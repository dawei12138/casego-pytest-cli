from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

from .models import ApiResource, LoadedProject, SourceResource
from .openapi_importer import (
    HTTP_METHODS,
    build_openapi_sync_key,
    iter_openapi_operations,
    normalize_openapi_operation_contract,
    path_segments,
    slug_segment,
)


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
                api_id=_build_api_id(module, path),
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
    by_sync_key: Dict[str, ApiResource] = {}
    by_method_path: Dict[Tuple[str, str], ApiResource] = {}
    for api in local_apis.values():
        sync_meta = (api.meta or {}).get("sync") or {}
        sync_key = sync_meta.get("syncKey")
        if sync_key and sync_key not in by_sync_key:
            by_sync_key[sync_key] = api
        method_path = _api_method_path(api)
        if method_path and method_path not in by_method_path:
            by_method_path[method_path] = api

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
                module=(local_api.meta or {}).get("module", operation.module),
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


def _build_api_id(module: str, path: str) -> str:
    segments = path_segments(path)
    api_leaf = ".".join(segments) if segments else "root"
    return f"{module}.{api_leaf}"


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
