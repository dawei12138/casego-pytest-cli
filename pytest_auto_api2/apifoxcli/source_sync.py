from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import hashlib
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

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
from .sync_report import SyncReport, build_sync_report, write_sync_report


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


def apply_source_sync(project: LoadedProject, source_id: str, plan: SyncPlan) -> SyncReport:
    if source_id not in project.sources:
        raise KeyError(f"source not found: {source_id}")

    root = project.root / "apifox"
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

    report = build_sync_report(project, source_id, plan)
    write_sync_report(root / "reports" / "sync", report)
    return report


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
