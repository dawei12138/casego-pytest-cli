from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

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
    for item in [*plan.created, *plan.updated]:
        payload = render_api_resource(project, source_id, item)
        write_api_resource(root / "apis", item.module, item.api_id, payload)
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
        write_api_resource(root / "apis", module, item.api_id, payload)
        project.apis[item.api_id] = ApiResource(**payload)

    report = build_sync_report(project, source_id, plan)
    write_sync_report(root / "reports" / "sync", report)
    return report


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


def write_api_resource(root: Path, module: str, api_id: str, payload: Dict[str, object]) -> Path:
    module_name = module or "_default"
    module_root = root / module_name
    module_root.mkdir(parents=True, exist_ok=True)
    file_name = api_id.split(".")[-1].replace("_", "-")
    path = module_root / f"{file_name}.yaml"
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


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
