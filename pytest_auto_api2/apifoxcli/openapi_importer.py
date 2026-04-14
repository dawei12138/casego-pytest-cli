from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

import requests
import yaml


HTTP_METHODS = ("get", "post", "put", "delete", "patch", "options", "head")
_OMIT = object()


def load_openapi_document(source: str, *, root: Optional[Path] = None) -> Dict[str, Any]:
    return _load_document(resolve_openapi_source_location(source, root=root))


def select_openapi_server(
    document: Dict[str, Any],
    server_description: Optional[str],
    server_url: Optional[str],
) -> Dict[str, Any]:
    return _select_server(document, server_description, server_url)


def resolve_openapi_base_url(server_url: str, source: str) -> str:
    return _resolve_base_url(server_url, source)


def has_openapi_bearer_security(document: Dict[str, Any]) -> bool:
    return _has_bearer_security(document)


def resolve_openapi_source_location(source: str, *, root: Optional[Path] = None) -> str:
    if source.startswith(("http://", "https://")):
        return source
    raw = Path(source)
    if raw.is_absolute():
        return str(raw)
    base = Path(root) if root is not None else Path.cwd()
    return str((base / raw).resolve())


def normalize_openapi_source_reference(root: Path, source: str) -> str:
    if source.startswith(("http://", "https://")):
        return source
    resolved = Path(resolve_openapi_source_location(source, root=Path(root)))
    project_root = Path(root).resolve()
    try:
        return resolved.relative_to(project_root).as_posix()
    except ValueError:
        return str(resolved)


def iter_openapi_operations(
    document: Dict[str, Any],
    include_paths: Optional[Iterable[str]] = None,
    exclude_paths: Optional[Iterable[str]] = None,
) -> Iterable[Tuple[str, str, Dict[str, Any]]]:
    allowed_paths = set(include_paths or [])
    blocked_paths = set(exclude_paths or [])
    for path, path_item in (document.get("paths") or {}).items():
        if allowed_paths and path not in allowed_paths:
            continue
        if path in blocked_paths:
            continue
        if not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            method_name = str(method).lower()
            if method_name not in HTTP_METHODS:
                continue
            yield path, method_name, operation or {}


def build_openapi_sync_key(method: str, path: str, operation: Dict[str, Any]) -> str:
    operation_id = (operation.get("operationId") or "").strip()
    if operation_id:
        return operation_id

    parts = path_segments(path)
    stem = "_".join(part.replace("-", "_") for part in parts) if parts else "root"
    return f"{stem}_{method.lower()}"


def normalize_openapi_operation_contract(
    document: Dict[str, Any],
    path: str,
    method: str,
    operation: Dict[str, Any],
) -> Dict[str, object]:
    request: Dict[str, object] = {"method": method.upper(), "path": path}
    content = ((operation.get("requestBody") or {}).get("content") or {})

    if "application/x-www-form-urlencoded" in content:
        request["contentType"] = "application/x-www-form-urlencoded"
        schema = _resolve_schema(document, content["application/x-www-form-urlencoded"].get("schema") or {})
        form_schema = normalize_openapi_schema_properties(document, schema)
        if form_schema:
            request["formSchema"] = form_schema
    elif "multipart/form-data" in content:
        request["contentType"] = "multipart/form-data"
        schema = _resolve_schema(document, content["multipart/form-data"].get("schema") or {})
        form_schema = normalize_openapi_schema_properties(document, schema)
        if form_schema:
            request["formSchema"] = form_schema
    elif "application/json" in content:
        request["contentType"] = "application/json"
        schema = _resolve_schema(document, content["application/json"].get("schema") or {})
        json_schema = normalize_openapi_schema_properties(document, schema)
        if json_schema:
            request["jsonSchema"] = json_schema

    responses = {str(status_code): {} for status_code in ((operation.get("responses") or {}).keys())}
    return {"request": request, "responses": responses}


def normalize_openapi_schema_properties(document: Dict[str, Any], schema: Dict[str, Any]) -> Dict[str, object]:
    resolved = _resolve_schema(document, schema)
    properties = resolved.get("properties") or {}
    if not isinstance(properties, dict):
        return {}

    required = set(resolved.get("required") or [])
    normalized: Dict[str, object] = {}
    for field_name, field_schema in properties.items():
        resolved_field = _resolve_schema(document, field_schema or {})
        field_type = resolved_field.get("type")
        if not field_type and "properties" in resolved_field:
            field_type = "object"
        normalized_field: Dict[str, object] = {"type": field_type or "string"}
        if field_name in required:
            normalized_field["required"] = True
        if "default" in resolved_field:
            normalized_field["default"] = resolved_field["default"]
        normalized[field_name] = normalized_field
    return normalized


def slug_segment(value: str) -> str:
    return _slug_segment(value)


def path_segments(path: str) -> List[str]:
    parts: List[str] = []
    for raw_part in path.strip("/").split("/"):
        if not raw_part:
            continue
        if raw_part.startswith("{") and raw_part.endswith("}"):
            raw_part = f"by-{raw_part[1:-1]}"
        parts.append(_slug_segment(raw_part))
    return parts


def import_openapi_project(
    root: Path,
    source: str,
    env_id: str = "qa",
    server_description: Optional[str] = None,
    server_url: Optional[str] = None,
    include_paths: Optional[Iterable[str]] = None,
) -> int:
    project_root = Path(root)
    apifox = project_root / "apifox"
    document = load_openapi_document(source, root=project_root)
    selected_server = select_openapi_server(document, server_description, server_url)
    base_url = resolve_openapi_base_url(selected_server.get("url", ""), source)

    _write_env(apifox / "envs" / f"{env_id}.yaml", env_id, base_url, has_openapi_bearer_security(document))

    imported = 0
    for path, method, operation in iter_openapi_operations(document, include_paths=include_paths):
        resource = _build_api_resource(
            document=document,
            source=source,
            env_id=env_id,
            path=path,
            method=method,
            operation=operation,
        )
        file_path = _resource_file_path(apifox / "apis", resource["id"])
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(
            yaml.safe_dump(resource, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        imported += 1

    return imported


def bootstrap_openapi_source(
    root: Path,
    source_id: str,
    source: str,
    env_id: str = "qa",
    server_description: Optional[str] = None,
    server_url: Optional[str] = None,
    include_paths: Optional[Iterable[str]] = None,
    document: Optional[Dict[str, Any]] = None,
) -> None:
    project_root = Path(root)
    apifox = project_root / "apifox"
    normalized_source = normalize_openapi_source_reference(project_root, source)
    loaded_document = document if document is not None else load_openapi_document(source, root=project_root)
    selected_server = select_openapi_server(loaded_document, server_description, server_url)
    resolved_server_url = str(selected_server.get("url") or "")
    resolved_server_description = str(selected_server.get("description") or "") or None
    base_url = resolve_openapi_base_url(resolved_server_url, normalized_source)

    _write_env(apifox / "envs" / f"{env_id}.yaml", env_id, base_url, has_openapi_bearer_security(loaded_document))
    _write_source(
        apifox / "sources" / f"{source_id}.yaml",
        source_id=source_id,
        source=normalized_source,
        server_description=resolved_server_description,
        server_url=resolved_server_url or None,
        include_paths=list(include_paths or []),
        tag_map=_infer_tag_map(loaded_document, include_paths=include_paths),
    )


def _load_document(source: str) -> Dict[str, Any]:
    if source.startswith(("http://", "https://")):
        response = requests.get(source, timeout=30)
        response.raise_for_status()
        text = response.text
    else:
        text = Path(source).read_text(encoding="utf-8")

    data = yaml.safe_load(text) or {}
    if not isinstance(data, dict):
        raise TypeError("OpenAPI document must be a mapping")
    return data


def _select_server(
    document: Dict[str, Any],
    server_description: Optional[str],
    server_url: Optional[str],
) -> Dict[str, Any]:
    servers = document.get("servers") or []
    if not servers:
        return {"url": "", "description": ""}

    if server_url:
        for item in servers:
            if item.get("url") == server_url:
                return item
        raise ValueError(f"OpenAPI server url not found: {server_url}")

    if server_description:
        for item in servers:
            if item.get("description") == server_description:
                return item
        raise ValueError(f"OpenAPI server description not found: {server_description}")

    return servers[0]


def _resolve_base_url(server_url: str, source: str) -> str:
    if not server_url:
        return ""
    if server_url.startswith(("http://", "https://")):
        return server_url.rstrip("/")

    parsed = urlparse(source)
    if parsed.scheme and parsed.netloc:
        return urljoin(f"{parsed.scheme}://{parsed.netloc}", server_url).rstrip("/")
    return server_url.rstrip("/")


def _write_source(
    path: Path,
    *,
    source_id: str,
    source: str,
    server_description: Optional[str],
    server_url: Optional[str],
    include_paths: List[str],
    tag_map: Dict[str, str],
) -> None:
    if path.exists():
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    else:
        payload = {"kind": "source", "id": source_id, "name": source_id, "spec": {}}
    if not isinstance(payload, dict):
        payload = {"kind": "source", "id": source_id, "name": source_id, "spec": {}}

    payload["kind"] = "source"
    payload["id"] = source_id
    payload["name"] = str(payload.get("name") or source_id)

    spec = payload.setdefault("spec", {})
    if not isinstance(spec, dict):
        spec = {}
        payload["spec"] = spec

    existing_tag_map = spec.get("tagMap")
    if not isinstance(existing_tag_map, dict):
        existing_tag_map = {}
    merged_tag_map = dict(existing_tag_map)
    merged_tag_map.update({key: value for key, value in tag_map.items() if value and value != "_default"})

    spec["type"] = "openapi"
    spec["url"] = source
    spec["syncMode"] = str(spec.get("syncMode") or "full")
    spec["missingPolicy"] = str(spec.get("missingPolicy") or "markRemoved")
    spec["serverDescription"] = server_description
    spec["serverUrl"] = server_url
    spec["includePaths"] = include_paths
    spec["excludePaths"] = list(spec.get("excludePaths") or [])
    spec["tagMap"] = merged_tag_map
    rebinds = spec.get("rebinds")
    spec["rebinds"] = rebinds if isinstance(rebinds, dict) else {}
    guards = spec.get("guards")
    if not isinstance(guards, dict):
        guards = {}
    guards.setdefault("maxRemoveCount", 20)
    guards.setdefault("maxRemoveRatio", 0.2)
    spec["guards"] = guards

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _write_env(path: Path, env_id: str, base_url: str, add_bearer_header: bool) -> None:
    if path.exists():
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    else:
        payload = {"kind": "env", "id": env_id, "name": env_id.upper(), "spec": {}}

    spec = payload.setdefault("spec", {})
    spec["baseUrl"] = base_url
    spec.setdefault("headers", {})
    spec.setdefault("variables", {})
    if add_bearer_header:
        spec["headers"].setdefault("Authorization", "Bearer ${context.token}")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _has_bearer_security(document: Dict[str, Any]) -> bool:
    schemes = ((document.get("components") or {}).get("securitySchemes") or {}).values()
    for scheme in schemes:
        if scheme.get("type") == "http" and scheme.get("scheme") == "bearer":
            return True
        if scheme.get("type") == "oauth2":
            return True
    return False


def _infer_tag_map(
    document: Dict[str, Any],
    include_paths: Optional[Iterable[str]] = None,
) -> Dict[str, str]:
    tag_map: Dict[str, str] = {}
    for path, method, operation in iter_openapi_operations(document, include_paths=include_paths):
        tags = operation.get("tags") or []
        for tag in tags:
            if not isinstance(tag, str) or not tag or tag in tag_map:
                continue
            tag_map[tag] = _infer_module_name(tag, path, method, operation)
    return tag_map


def _infer_module_name(tag: str, path: str, method: str, operation: Dict[str, Any]) -> str:
    tag_slug = _slug_segment(tag)
    if tag_slug != "item":
        return tag_slug
    folded = tag.casefold()
    if any(keyword in folded for keyword in ("auth", "login", "signin", "oauth", "token", "登录", "认证", "授权")):
        return "auth"
    operation_id = str(operation.get("operationId") or "").casefold()
    if any(keyword in operation_id for keyword in ("auth", "login", "signin", "token")):
        return "auth"
    segments = path_segments(path)
    if not segments:
        return "_default"
    first = segments[0]
    if first in {"v1", "v2", "v3", "api"} and len(segments) > 1:
        first = segments[1]
    if first in {"login", "signin", "sign-in", "logout", "token", "session", "oauth", "auth"}:
        return "auth"
    return first or slug_segment(method)


def _resource_file_path(root: Path, resource_id: str) -> Path:
    parts = resource_id.split(".")
    return root.joinpath(*parts).with_suffix(".yaml")


def _build_api_resource(
    document: Dict[str, Any],
    source: str,
    env_id: str,
    path: str,
    method: str,
    operation: Dict[str, Any],
) -> Dict[str, Any]:
    request: Dict[str, Any] = {
        "method": method.upper(),
        "path": _build_request_path(path, operation.get("parameters") or []),
    }

    header_params = _extract_header_parameters(operation.get("parameters") or [])
    if header_params:
        request["headers"] = header_params

    query_params = _extract_query_parameters(operation.get("parameters") or [])
    if query_params:
        request["query"] = query_params

    body_request = _extract_request_body(document, operation)
    if body_request.get("headers"):
        merged_headers = dict(request.get("headers") or {})
        merged_headers.update(body_request["headers"])
        request["headers"] = merged_headers
    for key, value in body_request.items():
        if key == "headers":
            continue
        request[key] = value

    return {
        "kind": "api",
        "id": _build_api_id(method, path),
        "name": operation.get("summary") or f"{method.upper()} {path}",
        "meta": {
            "source": {
                "kind": "openapi",
                "origin": source,
                "path": path,
                "method": method.upper(),
                "operationId": operation.get("operationId"),
                "tags": operation.get("tags") or [],
            }
        },
        "spec": {
            "protocol": "http",
            "envRef": env_id,
            "request": request,
            "expect": {"status": 200, "assertions": []},
            "extract": [],
        },
    }


def _build_request_path(path: str, parameters: Iterable[Dict[str, Any]]) -> str:
    request_path = path
    for param in parameters:
        if param.get("in") != "path":
            continue
        name = param["name"]
        request_path = request_path.replace(f"{{{name}}}", f"${{dataset.{name}}}")
    return request_path


def _extract_header_parameters(parameters: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    headers: Dict[str, Any] = {}
    for param in parameters:
        if param.get("in") != "header":
            continue
        value = _parameter_value(param)
        if value is not _OMIT:
            headers[param["name"]] = value
    return headers


def _extract_query_parameters(parameters: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    query: Dict[str, Any] = {}
    for param in parameters:
        if param.get("in") != "query":
            continue
        value = _parameter_value(param)
        if value is not _OMIT:
            query[param["name"]] = value
    return query


def _parameter_value(parameter: Dict[str, Any]) -> Any:
    schema = parameter.get("schema") or {}
    default = _schema_default(schema)
    if default is not _OMIT:
        return default
    if parameter.get("required"):
        return f"${{dataset.{parameter['name']}}}"
    return _OMIT


def _extract_request_body(document: Dict[str, Any], operation: Dict[str, Any]) -> Dict[str, Any]:
    content = ((operation.get("requestBody") or {}).get("content") or {})
    if not content:
        return {}

    if "application/json" in content:
        schema = _resolve_schema(document, content["application/json"].get("schema") or {})
        body = _schema_payload(schema)
        result: Dict[str, Any] = {"headers": {"Content-Type": "application/json"}}
        if body is not _OMIT:
            result["json"] = body
        return result

    if "application/x-www-form-urlencoded" in content:
        schema = _resolve_schema(document, content["application/x-www-form-urlencoded"].get("schema") or {})
        body = _schema_payload(schema)
        result = {"headers": {"Content-Type": "application/x-www-form-urlencoded"}}
        if body is not _OMIT:
            result["form"] = body
        return result

    if "multipart/form-data" in content:
        schema = _resolve_schema(document, content["multipart/form-data"].get("schema") or {})
        body = _schema_payload(schema)
        if body is _OMIT:
            return {}
        return {"form": body}

    return {}


def _resolve_schema(document: Dict[str, Any], schema: Dict[str, Any]) -> Dict[str, Any]:
    if "$ref" in schema:
        ref = schema["$ref"]
        if not ref.startswith("#/components/schemas/"):
            raise ValueError(f"Unsupported schema ref: {ref}")
        name = ref.split("/")[-1]
        return _resolve_schema(document, (document.get("components") or {}).get("schemas", {}).get(name) or {})

    for key in ("allOf", "oneOf", "anyOf"):
        options = schema.get(key) or []
        for option in options:
            resolved = _resolve_schema(document, option)
            if resolved.get("type") != "null":
                return resolved

    return schema


def _schema_payload(schema: Dict[str, Any]) -> Any:
    schema_type = schema.get("type")
    if schema_type == "object" or "properties" in schema:
        payload: Dict[str, Any] = {}
        required = set(schema.get("required") or [])
        for name, prop_schema in (schema.get("properties") or {}).items():
            value = _schema_property_value(name, prop_schema, name in required)
            if value is not _OMIT:
                payload[name] = value
        return payload

    default = _schema_default(schema)
    if default is not _OMIT:
        return default

    return _OMIT


def _schema_property_value(name: str, schema: Dict[str, Any], required: bool) -> Any:
    default = _schema_default(schema)
    if default is not _OMIT:
        return default

    schema_type = schema.get("type")
    if schema_type == "object" or "properties" in schema:
        nested = _schema_payload(schema)
        if nested is not _OMIT:
            return nested
    if schema_type == "array":
        item_default = _schema_default(schema.get("items") or {})
        if item_default is not _OMIT:
            return [item_default]
        return [] if required else _OMIT
    if required:
        return f"${{dataset.{name}}}"
    return _OMIT


def _schema_default(schema: Dict[str, Any]) -> Any:
    if "default" in schema:
        return schema["default"]
    for key in ("allOf", "oneOf", "anyOf"):
        for option in schema.get(key) or []:
            default = _schema_default(option)
            if default is not _OMIT:
                return default
    return _OMIT


def _build_api_id(method: str, path: str) -> str:
    parts = [_slug_segment(method)]
    parts.extend(path_segments(path))
    if len(parts) == 1:
        parts.append("root")
    return ".".join(parts)


def _slug_segment(value: str) -> str:
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", value)
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return value or "item"
