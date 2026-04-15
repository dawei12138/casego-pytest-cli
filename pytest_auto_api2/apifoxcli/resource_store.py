from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

import yaml

_PROJECT_ID = "default"
_DEFAULT_BASE_URL = "http://127.0.0.1:8000"
_APIFOX_DIRS = ("sources", "envs", "apis", "cases", "flows", "suites", "datasets", "mocks")
_STORAGE_ID_RE = re.compile(r"^[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*$")


def ensure_apifox_layout(root: Path) -> None:
    apifox = Path(root) / "apifox"
    apifox.mkdir(parents=True, exist_ok=True)
    for rel in _APIFOX_DIRS:
        (apifox / rel).mkdir(parents=True, exist_ok=True)


def project_file(root: Path) -> Path:
    return Path(root) / "apifox" / "project.yaml"


def env_file(root: Path, env_id: str) -> Path:
    return Path(root) / "apifox" / "envs" / f"{validate_storage_id(env_id, label='env id')}.yaml"


def source_file(root: Path, source_id: str) -> Path:
    return Path(root) / "apifox" / "sources" / f"{validate_storage_id(source_id, label='source id')}.yaml"


def resource_file(root: Path, collection: str, resource_id: str) -> Path:
    return (Path(root) / "apifox" / collection).joinpath(*_resource_id_parts(resource_id)).with_suffix(".yaml")


def case_file(root: Path, case_id: str) -> Path:
    return resource_file(root, "cases", case_id)


def flow_file(root: Path, flow_id: str) -> Path:
    return resource_file(root, "flows", flow_id)


def suite_file(root: Path, suite_id: str) -> Path:
    return resource_file(root, "suites", suite_id)


def smoke_suite_file(root: Path) -> Path:
    return Path(root) / "apifox" / "suites" / "smoke.yaml"


def require_project_initialized(root: Path) -> Path:
    path = project_file(root)
    if not path.exists():
        raise FileNotFoundError(f"project file not found: {path}")
    return path


def write_project(root: Path, *, name: str, default_env: str) -> Path:
    ensure_apifox_layout(root)
    path = project_file(root)
    existing = _read_mapping(path) if path.exists() else {}
    payload = {
        "kind": "project",
        "id": str(existing.get("id") or _PROJECT_ID),
        "name": str(name),
        "spec": {"defaultEnv": str(default_env)},
    }
    meta = existing.get("meta")
    if isinstance(meta, dict) and meta:
        payload["meta"] = dict(meta)
    _write_mapping(path, payload)
    return path


def write_env(
    root: Path,
    env_id: str,
    *,
    base_url: str,
    name: Optional[str] = None,
    headers: Optional[Mapping[str, Any]] = None,
    variables: Optional[Mapping[str, Any]] = None,
) -> Path:
    require_project_initialized(root)
    ensure_apifox_layout(root)
    path = env_file(root, env_id)
    existing = _read_mapping(path) if path.exists() else {}
    spec = _read_spec(existing)
    payload = {
        "kind": "env",
        "id": str(env_id),
        "name": str(name or existing.get("name") or env_id),
        "spec": {
            "baseUrl": str(base_url),
            "headers": dict(headers) if headers is not None else dict(spec.get("headers") or {}),
            "variables": dict(variables) if variables is not None else dict(spec.get("variables") or {}),
        },
    }
    meta = existing.get("meta")
    if isinstance(meta, dict) and meta:
        payload["meta"] = dict(meta)
    _write_mapping(path, payload)
    return path


def set_project_default_env(root: Path, env_id: str) -> Path:
    path = require_project_initialized(root)
    if not env_file(root, env_id).exists():
        raise FileNotFoundError(f"env not found: {env_id}")
    existing = _read_mapping(path)
    return write_project(
        root,
        name=str(existing.get("name") or _PROJECT_ID),
        default_env=env_id,
    )


def write_scaffold_smoke_suite(root: Path, *, env_ref: str) -> Path:
    ensure_apifox_layout(root)
    path = smoke_suite_file(root)
    existing = _read_mapping(path) if path.exists() else {}
    spec = _read_spec(existing)
    spec_payload = dict(spec)
    spec_payload["envRef"] = str(env_ref)
    spec_payload.setdefault("failFast", True)
    spec_payload.setdefault("concurrency", 1)
    spec_payload.setdefault("items", [])
    payload = {
        "kind": "suite",
        "id": str(existing.get("id") or "smoke"),
        "name": str(existing.get("name") or "Smoke"),
        "spec": spec_payload,
    }
    meta = existing.get("meta")
    if isinstance(meta, dict) and meta:
        payload["meta"] = dict(meta)
    _write_mapping(path, payload)
    return path


def write_case(
    root: Path,
    case_id: str,
    *,
    api_ref: str,
    request: Optional[Mapping[str, Any]] = None,
    name: Optional[str] = None,
) -> Path:
    require_project_initialized(root)
    ensure_apifox_layout(root)
    payload = {
        "kind": "case",
        "id": str(case_id),
        "name": str(name or case_id),
        "spec": {
            "apiRef": str(api_ref),
            "data": {},
            "request": dict(request or {}),
            "expect": {"status": 200, "assertions": []},
            "extract": [],
            "hooks": {"before": [], "after": []},
        },
    }
    path = case_file(root, case_id)
    _write_mapping(path, payload)
    return path


def write_flow(root: Path, flow_id: str, *, name: Optional[str] = None) -> Path:
    require_project_initialized(root)
    ensure_apifox_layout(root)
    payload = {
        "kind": "flow",
        "id": str(flow_id),
        "name": str(name or flow_id),
        "spec": {"steps": []},
    }
    path = flow_file(root, flow_id)
    _write_mapping(path, payload)
    return path


def append_flow_step(
    root: Path,
    flow_id: str,
    *,
    case_ref: Optional[str] = None,
    api_ref: Optional[str] = None,
) -> Path:
    if int(bool(case_ref)) + int(bool(api_ref)) != 1:
        raise ValueError("flow add requires exactly one of case_ref or api_ref")

    payload = _read_existing_resource(root, flow_file(root, flow_id), "flow", flow_id)
    spec = _read_required_spec(payload, owner=f"flow {flow_id}")
    steps = _read_list(spec, "steps")
    step_payload = {"caseRef": str(case_ref)} if case_ref else {"apiRef": str(api_ref)}
    steps.append(step_payload)
    spec["steps"] = steps
    updated = _merge_resource_payload(payload, "flow", flow_id, spec)
    _write_mapping(flow_file(root, flow_id), updated)
    return flow_file(root, flow_id)


def write_suite(root: Path, suite_id: str, *, name: Optional[str] = None) -> Path:
    require_project_initialized(root)
    ensure_apifox_layout(root)
    payload = {
        "kind": "suite",
        "id": str(suite_id),
        "name": str(name or suite_id),
        "spec": {"items": []},
    }
    path = suite_file(root, suite_id)
    _write_mapping(path, payload)
    return path


def append_suite_item(
    root: Path,
    suite_id: str,
    *,
    case_ref: Optional[str] = None,
    api_ref: Optional[str] = None,
    flow_ref: Optional[str] = None,
    dataset_ref: Optional[str] = None,
) -> Path:
    if int(bool(case_ref)) + int(bool(api_ref)) + int(bool(flow_ref)) != 1:
        raise ValueError("suite add requires exactly one of case_ref, api_ref, or flow_ref")

    payload = _read_existing_resource(root, suite_file(root, suite_id), "suite", suite_id)
    spec = _read_required_spec(payload, owner=f"suite {suite_id}")
    items = _read_list(spec, "items")
    item_payload: Dict[str, Any]
    if case_ref:
        item_payload = {"caseRef": str(case_ref)}
    elif api_ref:
        item_payload = {"apiRef": str(api_ref)}
    else:
        item_payload = {"flowRef": str(flow_ref)}
    if dataset_ref is not None:
        item_payload["datasetRef"] = str(dataset_ref)
    items.append(item_payload)
    spec["items"] = items
    updated = _merge_resource_payload(payload, "suite", suite_id, spec)
    _write_mapping(suite_file(root, suite_id), updated)
    return suite_file(root, suite_id)


def set_env_variable(root: Path, env_id: str, key: str, value: Any) -> Path:
    payload = _read_existing_env(root, env_id)
    spec = _read_spec(payload)
    variables = dict(spec.get("variables") or {})
    variables[str(key)] = value
    return write_env(
        root,
        env_id,
        base_url=str(spec.get("baseUrl") or _DEFAULT_BASE_URL),
        name=str(payload.get("name") or env_id),
        headers=dict(spec.get("headers") or {}),
        variables=variables,
    )


def get_env_variable(root: Path, env_id: str, key: str) -> Any:
    variables = list_env_variables(root, env_id)
    if key not in variables:
        raise KeyError(f"env variable not found: {env_id}.{key}")
    return variables[key]


def list_env_variables(root: Path, env_id: str) -> Dict[str, Any]:
    payload = _read_existing_env(root, env_id)
    spec = _read_spec(payload)
    return dict(spec.get("variables") or {})


def unset_env_variable(root: Path, env_id: str, key: str) -> Path:
    payload = _read_existing_env(root, env_id)
    spec = _read_spec(payload)
    variables = dict(spec.get("variables") or {})
    variables.pop(str(key), None)
    return write_env(
        root,
        env_id,
        base_url=str(spec.get("baseUrl") or _DEFAULT_BASE_URL),
        name=str(payload.get("name") or env_id),
        headers=dict(spec.get("headers") or {}),
        variables=variables,
    )


def set_env_header(root: Path, env_id: str, key: str, value: str) -> Path:
    payload = _read_existing_env(root, env_id)
    spec = _read_spec(payload)
    headers = dict(spec.get("headers") or {})
    headers[str(key)] = str(value)
    return write_env(
        root,
        env_id,
        base_url=str(spec.get("baseUrl") or _DEFAULT_BASE_URL),
        name=str(payload.get("name") or env_id),
        headers=headers,
        variables=dict(spec.get("variables") or {}),
    )


def _read_existing_env(root: Path, env_id: str) -> Dict[str, Any]:
    require_project_initialized(root)
    path = env_file(root, env_id)
    if not path.exists():
        raise FileNotFoundError(f"env not found: {env_id}")
    return _read_mapping(path)


def _read_existing_resource(root: Path, path: Path, kind: str, resource_id: str) -> Dict[str, Any]:
    require_project_initialized(root)
    if not path.exists():
        raise FileNotFoundError(f"{kind} not found: {resource_id}")
    return _read_mapping(path)


def _resource_id_parts(resource_id: str) -> list[str]:
    value = validate_storage_id(resource_id, label="resource id")
    return value.split(".")


def validate_storage_id(value: str, *, label: str) -> str:
    text = str(value)
    if not _STORAGE_ID_RE.fullmatch(text):
        raise ValueError(f"invalid {label}: {value}")
    return text


def _read_mapping(path: Path) -> Dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise TypeError(f"YAML root must be a mapping: {path}")
    return data


def _read_spec(payload: Mapping[str, Any]) -> Dict[str, Any]:
    spec = payload.get("spec") or {}
    if not isinstance(spec, dict):
        return {}
    return dict(spec)


def _read_required_spec(payload: Mapping[str, Any], *, owner: str) -> Dict[str, Any]:
    spec = payload.get("spec")
    if spec is None:
        return {}
    if not isinstance(spec, dict):
        raise TypeError(f"{owner} resource spec must be a mapping")
    return dict(spec)


def _read_list(spec: Mapping[str, Any], field: str) -> list:
    value = spec.get(field)
    if value is None:
        return []
    if not isinstance(value, list):
        raise TypeError(f"resource spec.{field} must be a list")
    return list(value)


def _merge_resource_payload(
    payload: Mapping[str, Any],
    kind: str,
    resource_id: str,
    spec: Mapping[str, Any],
) -> Dict[str, Any]:
    updated = {
        "kind": str(payload.get("kind") or kind),
        "id": str(payload.get("id") or resource_id),
        "name": str(payload.get("name") or resource_id),
        "spec": dict(spec),
    }
    meta = payload.get("meta")
    if isinstance(meta, dict) and meta:
        updated["meta"] = dict(meta)
    return updated


def _write_mapping(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(dict(payload), allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
