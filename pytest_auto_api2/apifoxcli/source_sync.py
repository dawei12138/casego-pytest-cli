from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import hashlib
from pathlib import Path
import re
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

import yaml

from .models import ApiResource, LoadedProject, SourceResource
from .openapi_importer import (
    HTTP_METHODS,
    build_openapi_sync_key,
    iter_openapi_operations,
    normalize_openapi_operation_contract,
    path_segments,
    slug_segment,
)
from .resource_store import source_file, validate_storage_id
from .sync_report import SyncReport, build_sync_report, write_sync_report


PATH_PARAM_RE = re.compile(r"(?<!\$)\{([^{}]+)\}(?!\})")
LEGACY_PUBLIC_TOKEN_RE = re.compile(r"\$\{(?:context|dataset|env)\.([^{}]+)\}")


@dataclass
class NormalizedOperation:
    api_id: str
    module: str
    sync_key: str
    method: str
    path: str
    tags: List[str]
    contract: Dict[str, object]


@dataclass
class SyncDiff:
    kind: str
    field: str
    breaking: bool


@dataclass
class SyncCandidate:
    api_id: str
    module: str
    sync_key: str
    contract: Dict[str, object]
    diffs: List[SyncDiff]


@dataclass
class SyncPlan:
    created: List[SyncCandidate] = field(default_factory=list)
    updated: List[SyncCandidate] = field(default_factory=list)
    upstream_removed: List[SyncCandidate] = field(default_factory=list)
    unchanged: List[SyncCandidate] = field(default_factory=list)


@dataclass
class SyncImpact:
    cases: List[Dict[str, object]] = field(default_factory=list)
    flows: List[Dict[str, object]] = field(default_factory=list)
    suites: List[Dict[str, object]] = field(default_factory=list)


def apply_source_sync(
    project: LoadedProject,
    source_id: str,
    plan: SyncPlan,
    *,
    prune: bool = False,
) -> SyncReport:
    if source_id not in project.sources:
        raise KeyError(f"source not found: {source_id}")

    root = project.root / "apifox"
    source = project.sources[source_id]
    impact = analyze_sync_impact(project, plan)
    prune_api_ids = set()
    if prune:
        prune_api_ids = _collect_prunable_upstream_removed_api_ids(project, plan)
        _enforce_prune_guards(source, plan, prune_api_ids)

    apis_root = root / "apis"
    api_paths_by_id, api_ids_by_path = index_api_files_by_id(apis_root)
    enforce_api_id_source_ownership(project, source_id, plan, index_api_source_owners(apis_root))
    for item in [*plan.created, *plan.updated]:
        payload = render_api_resource(project, source_id, item)
        path = resolve_api_resource_path(apis_root, item.module, item.api_id, api_ids_by_path)
        write_api_resource(path, payload)
        remove_old_api_files_for_id(
            apis_root,
            item.api_id,
            keep_path=path,
            api_paths_by_id=api_paths_by_id,
            api_ids_by_path=api_ids_by_path,
        )
        api_paths_by_id[item.api_id] = {path}
        api_ids_by_path[path] = item.api_id
        project.apis[item.api_id] = ApiResource(**payload)

    for item in plan.upstream_removed:
        if item.api_id in prune_api_ids:
            remove_all_api_files_for_id(
                apis_root,
                item.api_id,
                api_paths_by_id=api_paths_by_id,
                api_ids_by_path=api_ids_by_path,
            )
            project.apis.pop(item.api_id, None)
            continue
        api = project.apis.get(item.api_id)
        if api is None:
            continue
        payload = api.model_dump(by_alias=True, exclude_none=True)
        meta = payload.setdefault("meta", {})
        if not isinstance(meta, dict):
            meta = {}
        module = str(meta.get("module") or item.module or "_default")
        sync_meta = meta.get("sync")
        if not isinstance(sync_meta, dict):
            sync_meta = {}
        sync_meta["sourceId"] = source_id
        if item.sync_key:
            sync_meta.setdefault("syncKey", item.sync_key)
        sync_meta["lifecycle"] = "upstreamRemoved"
        meta["sync"] = sync_meta
        payload["meta"] = meta
        path = resolve_api_resource_path(apis_root, module, item.api_id, api_ids_by_path)
        write_api_resource(path, payload)
        remove_old_api_files_for_id(
            apis_root,
            item.api_id,
            keep_path=path,
            api_paths_by_id=api_paths_by_id,
            api_ids_by_path=api_ids_by_path,
        )
        api_paths_by_id[item.api_id] = {path}
        api_ids_by_path[path] = item.api_id
        project.apis[item.api_id] = ApiResource(**payload)

    _persist_impacted_case_audit(root / "cases", project, impact)
    report = build_sync_report(
        project,
        source_id,
        plan,
        impact=impact,
        pruned_api_ids=sorted(prune_api_ids),
    )
    write_sync_report(root / "reports" / "sync", report)
    return report


def read_latest_sync_report(root: Path, source_id: str) -> Dict[str, Any]:
    validated_source_id = validate_storage_id(source_id, label="source id")
    report_root = Path(root) / "apifox" / "reports" / "sync"
    matches = sorted(report_root.glob(f"{validated_source_id}-*.yaml"))
    if not matches:
        raise FileNotFoundError(f"no sync report found for source '{source_id}'")

    payload = yaml.safe_load(matches[-1].read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise TypeError(f"sync report payload must be a mapping: {matches[-1]}")
    return payload


def upsert_source_rebind(root: Path, source_id: str, api_id: str, sync_key: str) -> Path:
    source_path = source_file(root, source_id)
    if not source_path.exists():
        raise FileNotFoundError(f"source not found: {source_id}")

    payload = yaml.safe_load(source_path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise TypeError(f"source payload must be a mapping: {source_path}")
    spec = payload.setdefault("spec", {})
    if not isinstance(spec, dict):
        spec = {}
        payload["spec"] = spec
    rebinds = spec.get("rebinds")
    if not isinstance(rebinds, dict):
        rebinds = {}
    rebinds[str(sync_key)] = str(api_id)
    spec["rebinds"] = rebinds

    source_path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return source_path


def enforce_api_id_source_ownership(
    project: LoadedProject,
    source_id: str,
    plan: SyncPlan,
    disk_owners_by_id: Dict[str, Set[str]],
) -> None:
    target_api_ids = {
        item.api_id
        for item in [*plan.created, *plan.updated, *plan.upstream_removed]
    }
    for api_id in sorted(target_api_ids):
        owners = set(disk_owners_by_id.get(api_id, set()))
        loaded = project.apis.get(api_id)
        loaded_owner = _api_source_id_from_resource(loaded)
        if loaded_owner:
            owners.add(loaded_owner)
        foreign = sorted(owner for owner in owners if owner and owner != source_id)
        if foreign:
            owner_list = ", ".join(foreign)
            raise ValueError(
                f"source ownership conflict for api_id '{api_id}': "
                f"owned by source(s) [{owner_list}], cannot sync source '{source_id}'"
            )


def analyze_sync_impact(project: LoadedProject, plan: SyncPlan) -> SyncImpact:
    case_reasons: Dict[str, List[Dict[str, object]]] = {}
    for item in plan.updated:
        reasons = _build_case_impact_reasons(item.diffs)
        if not reasons:
            continue
        for case in project.cases.values():
            if case.spec.apiRef != item.api_id:
                continue
            case_reasons.setdefault(case.id, [])
            _append_unique_reasons(case_reasons[case.id], reasons)

    case_entries: List[Dict[str, object]] = []
    impacted_case_ids: Set[str] = set()
    for case_id in sorted(case_reasons):
        reasons = case_reasons[case_id]
        case_entries.append({"caseId": case_id, "reasons": deepcopy(reasons)})
        impacted_case_ids.add(case_id)

    impacted_flow_ids: Set[str] = set()
    flow_entries: List[Dict[str, object]] = []
    for flow in sorted(project.flows.values(), key=lambda item: item.id):
        case_refs = {step.caseRef for step in flow.spec.steps if step.caseRef}
        if case_refs & impacted_case_ids:
            impacted_flow_ids.add(flow.id)
            flow_entries.append({"flowId": flow.id})

    suite_entries: List[Dict[str, object]] = []
    for suite in sorted(project.suites.values(), key=lambda item: item.id):
        has_impact = False
        for item in suite.spec.items:
            if item.caseRef and item.caseRef in impacted_case_ids:
                has_impact = True
                break
            if item.flowRef and item.flowRef in impacted_flow_ids:
                has_impact = True
                break
        if has_impact:
            suite_entries.append({"suiteId": suite.id})

    return SyncImpact(cases=case_entries, flows=flow_entries, suites=suite_entries)


def _build_case_impact_reasons(diffs: List[SyncDiff]) -> List[Dict[str, object]]:
    reasons: List[Dict[str, object]] = []
    for diff in diffs:
        if diff.kind == "request.requiredAdded":
            reasons.append({"type": "missing_required_input", "field": diff.field})
    return reasons


def _append_unique_reasons(existing: List[Dict[str, object]], new_reasons: List[Dict[str, object]]) -> None:
    for reason in new_reasons:
        if reason not in existing:
            existing.append(deepcopy(reason))


def _persist_impacted_case_audit(cases_root: Path, project: LoadedProject, impact: SyncImpact) -> None:
    if not impact.cases:
        return
    case_paths_by_id = index_resource_files_by_id(cases_root)
    for entry in impact.cases:
        case_id = entry.get("caseId")
        if not isinstance(case_id, str):
            continue
        case_path = case_paths_by_id.get(case_id)
        if case_path is None:
            continue
        try:
            payload = yaml.safe_load(case_path.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        meta = payload.get("meta")
        if not isinstance(meta, dict):
            meta = {}
        audit = meta.get("audit")
        if not isinstance(audit, dict):
            audit = {}
        audit["status"] = "impacted"
        audit["reasons"] = deepcopy(entry.get("reasons") if isinstance(entry.get("reasons"), list) else [])
        meta["audit"] = audit
        payload["meta"] = meta
        case_path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")

        case = project.cases.get(case_id)
        if case is not None:
            case_meta = case.meta if isinstance(case.meta, dict) else {}
            case_meta["audit"] = deepcopy(audit)
            case.meta = case_meta


def _collect_prunable_upstream_removed_api_ids(project: LoadedProject, plan: SyncPlan) -> Set[str]:
    referenced_api_ids = _collect_referenced_api_ids(project)
    return {item.api_id for item in plan.upstream_removed if item.api_id not in referenced_api_ids}


def _collect_referenced_api_ids(project: LoadedProject) -> Set[str]:
    referenced: Set[str] = set()
    for case in project.cases.values():
        if case.spec.apiRef:
            referenced.add(case.spec.apiRef)
    for flow in project.flows.values():
        for step in flow.spec.steps:
            if step.apiRef:
                referenced.add(step.apiRef)
    for suite in project.suites.values():
        for item in suite.spec.items:
            if item.apiRef:
                referenced.add(item.apiRef)
    return referenced


def _enforce_prune_guards(source: SourceResource, plan: SyncPlan, prune_api_ids: Set[str]) -> None:
    prune_count = len(prune_api_ids)
    if prune_count == 0:
        return

    max_remove_count = int(source.spec.guards.maxRemoveCount)
    if max_remove_count >= 0 and prune_count > max_remove_count:
        raise ValueError(
            f"prune guard exceeded: remove count {prune_count} exceeds maxRemoveCount {max_remove_count}"
        )

    managed_existing = len(plan.updated) + len(plan.unchanged) + len(plan.upstream_removed)
    if managed_existing <= 0:
        return
    remove_ratio = prune_count / managed_existing
    max_remove_ratio = float(source.spec.guards.maxRemoveRatio)
    if remove_ratio > max_remove_ratio:
        raise ValueError(
            f"prune guard exceeded: remove ratio {remove_ratio:.3f} exceeds maxRemoveRatio {max_remove_ratio}"
        )


def normalize_openapi_document(source: SourceResource, document: Dict[str, object]) -> List[NormalizedOperation]:
    operations: List[NormalizedOperation] = []
    for path, method, operation in iter_openapi_operations(
        document,
        include_paths=source.spec.includePaths,
        exclude_paths=source.spec.excludePaths,
    ):
        tags = [item for item in (operation.get("tags") or []) if isinstance(item, str)]
        module = _resolve_module(tags, source.spec.tagMap)
        operations.append(
            NormalizedOperation(
                api_id=_build_api_id(module, method, path),
                module=module,
                sync_key=build_openapi_sync_key(method, path, operation),
                method=method.upper(),
                path=path,
                tags=tags,
                contract=normalize_openapi_operation_contract(document, path, method, operation),
            )
        )
    return operations


def plan_source_sync(
    project: LoadedProject,
    source_id: str,
    operations: Iterable[NormalizedOperation],
) -> SyncPlan:
    if source_id not in project.sources:
        raise KeyError(f"source not found: {source_id}")

    source = project.sources[source_id]
    local_apis = {
        api.id: api
        for api in project.apis.values()
        if ((api.meta or {}).get("sync") or {}).get("sourceId") == source_id
    }
    by_id = dict(local_apis)
    by_sync_key, by_method_path = _index_local_apis(local_apis, source_id)

    plan = SyncPlan()
    seen_api_ids = set()
    for operation in operations:
        local_api = by_sync_key.get(operation.sync_key)
        if local_api is None:
            local_api = by_method_path.get((operation.method.upper(), operation.path))
        if local_api is None:
            local_api = _match_via_rebind(
                source.spec.rebinds or {},
                operation,
                by_id=by_id,
                by_sync_key=by_sync_key,
                by_method_path=by_method_path,
            )

        if local_api is None:
            plan.created.append(
                SyncCandidate(
                    api_id=operation.api_id,
                    module=operation.module,
                    sync_key=operation.sync_key,
                    contract=operation.contract,
                    diffs=[],
                )
            )
            continue

        seen_api_ids.add(local_api.id)
        diffs = diff_api_contract(local_api.spec.contract or {}, operation.contract)
        target = plan.unchanged if not diffs else plan.updated
        target.append(
            SyncCandidate(
                api_id=local_api.id,
                module=operation.module,
                sync_key=operation.sync_key,
                contract=operation.contract,
                diffs=diffs,
            )
        )

    for api_id, api in local_apis.items():
        if api_id in seen_api_ids:
            continue
        plan.upstream_removed.append(
            SyncCandidate(
                api_id=api_id,
                module=(api.meta or {}).get("module", "_default"),
                sync_key=((api.meta or {}).get("sync") or {}).get("syncKey", ""),
                contract=api.spec.contract or {},
                diffs=[],
            )
        )
    return plan


def render_api_resource(project: LoadedProject, source_id: str, item: SyncCandidate) -> Dict[str, object]:
    existing = project.apis.get(item.api_id)
    if existing is not None:
        payload: Dict[str, object] = existing.model_dump(by_alias=True, exclude_none=True)
    else:
        payload = {
            "kind": "api",
            "id": item.api_id,
            "name": item.api_id.split(".")[-1],
            "meta": {},
            "spec": {"protocol": "http"},
        }

    meta = payload.get("meta")
    if not isinstance(meta, dict):
        meta = {}
    module = item.module or str(meta.get("module") or "_default")
    meta["module"] = module

    sync_meta = meta.get("sync")
    if not isinstance(sync_meta, dict):
        sync_meta = {}
    sync_meta["sourceId"] = source_id
    sync_meta["syncKey"] = item.sync_key
    request = (item.contract or {}).get("request")
    if isinstance(request, dict):
        method = request.get("method")
        path = request.get("path")
        if method:
            sync_meta["upstreamMethod"] = str(method).upper()
        if path:
            sync_meta["upstreamPath"] = str(path)
    sync_meta["lifecycle"] = "active"
    meta["sync"] = sync_meta
    payload["meta"] = meta

    spec = payload.get("spec")
    if not isinstance(spec, dict):
        spec = {}
    spec["protocol"] = spec.get("protocol") or "http"
    spec["contract"] = deepcopy(item.contract)
    if not spec.get("envRef"):
        spec["envRef"] = project.project.spec.defaultEnv
    request_payload = _request_spec_from_contract(item.contract)
    if request_payload:
        existing_request = spec.get("request")
        previous_generated_request = (
            _request_spec_from_contract(existing.spec.contract or {}) if existing is not None else None
        )
        if (
            existing_request is None
            or _request_snapshot_matches_generated(existing_request, previous_generated_request)
        ):
            spec["request"] = request_payload
    if not spec.get("expect"):
        spec["expect"] = {"status": 200, "assertions": []}
    if not isinstance(spec.get("extract"), list):
        spec["extract"] = []
    payload["spec"] = spec
    payload["kind"] = "api"
    payload["id"] = item.api_id
    payload["name"] = str(payload.get("name") or item.api_id.split(".")[-1])
    return payload


def write_api_resource(path: Path, payload: Dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def resolve_api_resource_path(
    apis_root: Path,
    module_name: str,
    api_id: str,
    api_ids_by_path: Dict[Path, str],
) -> Path:
    normalized_module = module_name or "_default"
    module_root = apis_root / normalized_module
    base_stem = _build_api_file_stem(normalized_module, api_id)
    candidate = module_root / f"{base_stem}.yaml"
    if _path_available_for_api(candidate, api_id, api_ids_by_path):
        return candidate

    digest = hashlib.sha1(api_id.encode("utf-8")).hexdigest()[:8]
    alt = module_root / f"{base_stem}-{digest}.yaml"
    if _path_available_for_api(alt, api_id, api_ids_by_path):
        return alt

    index = 2
    while True:
        fallback = module_root / f"{base_stem}-{digest}-{index}.yaml"
        if _path_available_for_api(fallback, api_id, api_ids_by_path):
            return fallback
        index += 1


def index_api_files_by_id(apis_root: Path) -> Tuple[Dict[str, Set[Path]], Dict[Path, str]]:
    api_paths_by_id: Dict[str, Set[Path]] = {}
    api_ids_by_path: Dict[Path, str] = {}
    if not apis_root.exists():
        return api_paths_by_id, api_ids_by_path
    for file_path in sorted(apis_root.rglob("*.yaml")):
        api_id, _ = _read_api_identity_from_yaml(file_path)
        if not api_id:
            continue
        api_ids_by_path[file_path] = api_id
        api_paths_by_id.setdefault(api_id, set()).add(file_path)
    return api_paths_by_id, api_ids_by_path


def index_api_source_owners(apis_root: Path) -> Dict[str, Set[str]]:
    owners_by_id: Dict[str, Set[str]] = {}
    if not apis_root.exists():
        return owners_by_id
    for file_path in sorted(apis_root.rglob("*.yaml")):
        api_id, source_id = _read_api_identity_from_yaml(file_path)
        if not api_id or not source_id:
            continue
        owners_by_id.setdefault(api_id, set()).add(source_id)
    return owners_by_id


def index_resource_files_by_id(root: Path) -> Dict[str, Path]:
    paths_by_id: Dict[str, Path] = {}
    if not root.exists():
        return paths_by_id
    for file_path in sorted(root.rglob("*.yaml")):
        resource_id = _read_resource_id_from_yaml(file_path)
        if resource_id:
            paths_by_id.setdefault(resource_id, file_path)
    return paths_by_id


def remove_all_api_files_for_id(
    apis_root: Path,
    api_id: str,
    *,
    api_paths_by_id: Dict[str, Set[Path]],
    api_ids_by_path: Dict[Path, str],
) -> None:
    old_paths = sorted(api_paths_by_id.get(api_id, set()))
    for old_path in old_paths:
        if old_path.exists():
            old_path.unlink()
            _prune_empty_parents(old_path.parent, stop_dir=apis_root)
        api_ids_by_path.pop(old_path, None)
    api_paths_by_id.pop(api_id, None)


def remove_old_api_files_for_id(
    apis_root: Path,
    api_id: str,
    *,
    keep_path: Path,
    api_paths_by_id: Dict[str, Set[Path]],
    api_ids_by_path: Dict[Path, str],
) -> None:
    old_paths = sorted(api_paths_by_id.get(api_id, set()))
    for old_path in old_paths:
        if old_path == keep_path:
            continue
        if old_path.exists():
            old_path.unlink()
            _prune_empty_parents(old_path.parent, stop_dir=apis_root)
        api_ids_by_path.pop(old_path, None)
    api_paths_by_id[api_id] = {keep_path}


def _path_available_for_api(path: Path, api_id: str, api_ids_by_path: Dict[Path, str]) -> bool:
    existing_id = api_ids_by_path.get(path)
    if existing_id:
        return existing_id == api_id
    if not path.exists():
        return True
    file_api_id, _ = _read_api_identity_from_yaml(path)
    if not file_api_id:
        return False
    api_ids_by_path[path] = file_api_id
    return file_api_id == api_id


def _read_api_id_from_yaml(path: Path) -> Optional[str]:
    api_id, _ = _read_api_identity_from_yaml(path)
    return api_id


def _read_resource_id_from_yaml(path: Path) -> Optional[str]:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    value = payload.get("id")
    if isinstance(value, str) and value:
        return value
    return None


def _read_api_identity_from_yaml(path: Path) -> Tuple[Optional[str], Optional[str]]:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return None, None
    if not isinstance(payload, dict):
        return None, None
    value = payload.get("id")
    api_id = str(value) if isinstance(value, str) and value else None
    sync_source_id = _api_source_id_from_payload(payload)
    return api_id, sync_source_id


def _api_source_id_from_payload(payload: Dict[str, object]) -> Optional[str]:
    meta = payload.get("meta")
    if not isinstance(meta, dict):
        return None
    sync_meta = meta.get("sync")
    if not isinstance(sync_meta, dict):
        return None
    source_id = sync_meta.get("sourceId")
    if isinstance(source_id, str) and source_id:
        return source_id
    return None


def _api_source_id_from_resource(resource: Optional[ApiResource]) -> Optional[str]:
    if resource is None:
        return None
    sync_meta = (resource.meta or {}).get("sync")
    if not isinstance(sync_meta, dict):
        return None
    source_id = sync_meta.get("sourceId")
    if isinstance(source_id, str) and source_id:
        return source_id
    return None


def _prune_empty_parents(path: Path, *, stop_dir: Path) -> None:
    current = path
    while current != stop_dir and current.exists():
        if any(current.iterdir()):
            break
        current.rmdir()
        current = current.parent


def _build_api_file_stem(module_name: str, api_id: str) -> str:
    prefix = f"{module_name}."
    if module_name and api_id.startswith(prefix):
        suffix = api_id[len(prefix) :]
    else:
        suffix = api_id
    stem = suffix.replace(".", "-").replace("_", "-").strip("-")
    return stem or "api"


def diff_api_contract(local_contract: Dict[str, object], upstream_contract: Dict[str, object]) -> List[SyncDiff]:
    diffs: List[SyncDiff] = []
    local_request = (local_contract or {}).get("request") or {}
    upstream_request = (upstream_contract or {}).get("request") or {}

    for field, kind in (
        ("method", "request.methodChanged"),
        ("path", "request.pathChanged"),
        ("contentType", "request.contentTypeChanged"),
    ):
        if local_request.get(field) != upstream_request.get(field):
            diffs.append(SyncDiff(kind=kind, field=field, breaking=True))

    diffs.extend(_diff_required_fields(local_request.get("formSchema"), upstream_request.get("formSchema")))
    diffs.extend(_diff_required_fields(local_request.get("jsonSchema"), upstream_request.get("jsonSchema")))
    diffs.extend(_diff_required_fields(local_request.get("querySchema"), upstream_request.get("querySchema")))
    diffs.extend(_diff_required_path_params(local_request.get("path"), upstream_request.get("path")))
    return diffs


def _diff_required_fields(local_schema: object, upstream_schema: object) -> List[SyncDiff]:
    local_required = _required_fields(local_schema)
    upstream_required = _required_fields(upstream_schema)
    diffs: List[SyncDiff] = []
    for field_name in sorted(upstream_required - local_required):
        diffs.append(SyncDiff(kind="request.requiredAdded", field=field_name, breaking=True))
    for field_name in sorted(local_required - upstream_required):
        diffs.append(SyncDiff(kind="request.requiredRemoved", field=field_name, breaking=False))
    return diffs


def _required_fields(schema: object) -> set[str]:
    if not isinstance(schema, dict):
        return set()
    return {
        field_name
        for field_name, field_spec in schema.items()
        if isinstance(field_spec, dict) and bool(field_spec.get("required"))
    }


def _diff_required_path_params(local_path: object, upstream_path: object) -> List[SyncDiff]:
    local_required = _path_params(local_path)
    upstream_required = _path_params(upstream_path)
    diffs: List[SyncDiff] = []
    for field_name in sorted(upstream_required - local_required):
        diffs.append(SyncDiff(kind="request.requiredAdded", field=field_name, breaking=True))
    for field_name in sorted(local_required - upstream_required):
        diffs.append(SyncDiff(kind="request.requiredRemoved", field=field_name, breaking=False))
    return diffs


def _path_params(path: object) -> Set[str]:
    if not isinstance(path, str):
        return set()
    return set(PATH_PARAM_RE.findall(path))


def _api_method_path(api: ApiResource) -> Optional[Tuple[str, str]]:
    sync_meta = (api.meta or {}).get("sync") or {}
    contract_request = ((api.spec.contract or {}).get("request") or {})
    method = sync_meta.get("upstreamMethod") or contract_request.get("method")
    path = sync_meta.get("upstreamPath") or contract_request.get("path")
    if not method or not path:
        return None
    return str(method).upper(), str(path)


def _resolve_module(tags: List[str], tag_map: Dict[str, str]) -> str:
    for tag in tags:
        mapped = tag_map.get(tag)
        if mapped:
            return mapped
    if tags:
        fallback = slug_segment(tags[0])
        if fallback != "item":
            return fallback
    return "_default"


def _build_api_id(module: str, method: str, path: str) -> str:
    method_segment = slug_segment(method)
    segments = path_segments(path)
    api_leaf = ".".join(segments) if segments else "root"
    return f"{module}.{method_segment}.{api_leaf}"


def _index_local_apis(
    local_apis: Dict[str, ApiResource], source_id: str
) -> Tuple[Dict[str, ApiResource], Dict[Tuple[str, str], ApiResource]]:
    by_sync_key: Dict[str, ApiResource] = {}
    by_method_path: Dict[Tuple[str, str], ApiResource] = {}
    duplicate_sync_keys: Dict[str, List[str]] = {}
    duplicate_method_paths: Dict[Tuple[str, str], List[str]] = {}

    for api in sorted(local_apis.values(), key=lambda item: item.id):
        sync_meta = (api.meta or {}).get("sync") or {}
        sync_key = sync_meta.get("syncKey")
        if sync_key:
            if sync_key in by_sync_key:
                duplicate_sync_keys.setdefault(sync_key, [by_sync_key[sync_key].id]).append(api.id)
            else:
                by_sync_key[sync_key] = api

        method_path = _api_method_path(api)
        if method_path:
            if method_path in by_method_path:
                duplicate_method_paths.setdefault(method_path, [by_method_path[method_path].id]).append(api.id)
            else:
                by_method_path[method_path] = api

    if duplicate_sync_keys:
        detail = "; ".join(
            f"{sync_key} ({', '.join(sorted(set(api_ids)))})"
            for sync_key, api_ids in sorted(duplicate_sync_keys.items())
        )
        raise ValueError(f"duplicate local sync key for source '{source_id}': {detail}")

    if duplicate_method_paths:
        detail = "; ".join(
            f"{method} {path} ({', '.join(sorted(set(api_ids)))})"
            for (method, path), api_ids in sorted(duplicate_method_paths.items())
        )
        raise ValueError(f"duplicate local method+path for source '{source_id}': {detail}")

    return by_sync_key, by_method_path


def _match_via_rebind(
    rebinds: Dict[str, str],
    operation: NormalizedOperation,
    *,
    by_id: Dict[str, ApiResource],
    by_sync_key: Dict[str, ApiResource],
    by_method_path: Dict[Tuple[str, str], ApiResource],
) -> Optional[ApiResource]:
    probe_keys = (
        operation.sync_key,
        f"{operation.method.upper()} {operation.path}",
        f"{operation.method.lower()} {operation.path}",
        f"{operation.method.upper()}:{operation.path}",
    )

    for probe_key in probe_keys:
        target = rebinds.get(probe_key)
        matched = _resolve_rebind_target(target, by_id, by_sync_key, by_method_path)
        if matched:
            return matched

    for api_id, bound in rebinds.items():
        if bound in probe_keys and api_id in by_id:
            return by_id[api_id]

    return None


def _resolve_rebind_target(
    target: Optional[str],
    by_id: Dict[str, ApiResource],
    by_sync_key: Dict[str, ApiResource],
    by_method_path: Dict[Tuple[str, str], ApiResource],
) -> Optional[ApiResource]:
    if not target:
        return None
    if target in by_id:
        return by_id[target]
    if target in by_sync_key:
        return by_sync_key[target]

    method_path = _parse_method_path(target)
    if method_path:
        return by_method_path.get(method_path)
    return None


def _parse_method_path(raw: str) -> Optional[Tuple[str, str]]:
    for delimiter in (" ", ":"):
        if delimiter not in raw:
            continue
        method, path = raw.split(delimiter, 1)
        normalized_method = method.strip().lower()
        normalized_path = path.strip()
        if normalized_method in HTTP_METHODS and normalized_path.startswith("/"):
            return normalized_method.upper(), normalized_path
    return None


def _request_spec_from_contract(contract: Dict[str, object]) -> Optional[Dict[str, object]]:
    request = (contract or {}).get("request")
    if not isinstance(request, dict):
        return None
    method = str(request.get("method") or "").upper()
    path = str(request.get("path") or "")
    if not method or not path:
        return None

    payload: Dict[str, object] = {"method": method, "path": _request_path_snapshot(path)}
    content_type = request.get("contentType")
    if isinstance(content_type, str) and content_type:
        payload["headers"] = {"Content-Type": content_type}

    form_payload = _payload_from_contract_schema(request.get("formSchema"))
    if form_payload:
        payload["form"] = form_payload

    json_payload = _payload_from_contract_schema(request.get("jsonSchema"))
    if json_payload:
        payload["json"] = json_payload
    return payload


def _payload_from_contract_schema(schema: object) -> Dict[str, object]:
    if not isinstance(schema, dict):
        return {}
    payload: Dict[str, object] = {}
    for field_name, field_schema in schema.items():
        if not isinstance(field_schema, dict):
            continue
        if "default" in field_schema:
            payload[field_name] = field_schema["default"]
            continue
        if field_schema.get("required"):
            payload[field_name] = f"${{{{{field_name}}}}}"
    return payload


def _request_path_snapshot(path: str) -> str:
    return PATH_PARAM_RE.sub(lambda match: f"${{{{{match.group(1)}}}}}", path)


def _request_snapshot_matches_generated(existing_request: object, generated_request: object) -> bool:
    if not isinstance(existing_request, dict) or not isinstance(generated_request, dict):
        return False
    return _canonicalize_request_snapshot(existing_request) == _canonicalize_request_snapshot(generated_request)


def _canonicalize_request_snapshot(value: object, *, path_value: bool = False) -> object:
    if isinstance(value, dict):
        return {
            key: _canonicalize_request_snapshot(item, path_value=(key == "path"))
            for key, item in value.items()
            if item not in (None, {}, [])
        }
    if isinstance(value, list):
        return [_canonicalize_request_snapshot(item) for item in value]
    if isinstance(value, str):
        canonical = LEGACY_PUBLIC_TOKEN_RE.sub(
            lambda match: f"${{{{{match.group(1)}}}}}",
            value,
        )
        if path_value:
            canonical = _request_path_snapshot(canonical)
        return canonical
    return value
