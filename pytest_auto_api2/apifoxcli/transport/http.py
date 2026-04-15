from __future__ import annotations

import re

import requests

from ..contract import PreparedRequest
from ..resolver import resolve_value


RAW_PATH_TEMPLATE_RE = re.compile(r"(?<!\$)\{([^{}]+)\}(?!\})")


def _compact_mapping(value):
    if not value:
        return None
    return {key: item for key, item in value.items() if item not in (None, "")} or None


def prepare_http_api_request(api_or_request, context) -> PreparedRequest:
    return _normalize_request_payload(api_or_request, context)


def build_http_request_url(request_data: PreparedRequest, context) -> str:
    base_url = context.env["baseUrl"].rstrip("/")
    path = request_data.path.lstrip("/")
    return f"{base_url}/{path}"


def materialize_http_request(request_data: PreparedRequest, context):
    return {
        "method": request_data.method,
        "url": build_http_request_url(request_data, context),
        "headers": _compact_mapping(request_data.headers),
        "params": _compact_mapping(request_data.query) if request_data.query else None,
        "json": request_data.json_body,
        "data": _compact_mapping(request_data.form) if request_data.form else None,
    }


def _guard_public_request_path(path: str) -> str:
    match = RAW_PATH_TEMPLATE_RE.search(path)
    if match:
        raise ValueError(f"raw path template not allowed in request snapshot: {match.group(0)}")
    return path


def _build_direct_api_request(api, context) -> PreparedRequest:
    request_spec = api.spec.request
    if request_spec is None:
        raise ValueError(
            f"missing request data for direct api execution: api '{api.id}' must define spec.request"
        )

    raw_headers = {}
    raw_headers.update(context.env.get("headers") or {})
    raw_headers.update(request_spec.headers or {})
    return PreparedRequest(
        method=request_spec.method,
        path=_guard_public_request_path(resolve_value(request_spec.path, context, missing="error")),
        headers=resolve_value(raw_headers, context, missing="none"),
        query=resolve_value(request_spec.query, context) if request_spec.query else None,
        json_body=resolve_value(request_spec.json_body, context) if request_spec.json_body else None,
        form=resolve_value(request_spec.form, context) if request_spec.form else None,
    )


def _normalize_request_payload(request_input, context) -> PreparedRequest:
    if isinstance(request_input, PreparedRequest):
        return PreparedRequest(
            method=request_input.method,
            path=_guard_public_request_path(resolve_value(request_input.path, context, missing="error")),
            headers=resolve_value(request_input.headers or {}, context, missing="none"),
            query=resolve_value(request_input.query, context) if request_input.query else None,
            json_body=resolve_value(request_input.json_body, context) if request_input.json_body else None,
            form=resolve_value(request_input.form, context) if request_input.form else None,
        )
    return _build_direct_api_request(request_input, context)


def execute_prepared_http_request(request_data: PreparedRequest, context, timeout: int = 30):
    request_kwargs = materialize_http_request(request_data, context)
    return requests.request(
        method=request_kwargs["method"],
        url=request_kwargs["url"],
        headers=request_kwargs["headers"],
        params=request_kwargs["params"],
        json=request_kwargs["json"],
        data=request_kwargs["data"],
        timeout=timeout,
    )


def execute_http_api(api_or_request, context, timeout: int = 30):
    request_data = prepare_http_api_request(api_or_request, context)
    return execute_prepared_http_request(request_data, context, timeout=timeout)
