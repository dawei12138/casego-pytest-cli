from __future__ import annotations

import requests

from ..contract import PreparedRequest
from ..resolver import resolve_value


def _compact_mapping(value):
    if not value:
        return None
    return {key: item for key, item in value.items() if item not in (None, "")} or None


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
        path=request_spec.path,
        headers=resolve_value(raw_headers, context, missing="none"),
        query=resolve_value(request_spec.query, context) if request_spec.query else None,
        json_body=resolve_value(request_spec.json_body, context) if request_spec.json_body else None,
        form=resolve_value(request_spec.form, context) if request_spec.form else None,
    )


def _normalize_request_payload(request_input, context) -> PreparedRequest:
    if isinstance(request_input, PreparedRequest):
        return PreparedRequest(
            method=request_input.method,
            path=request_input.path,
            headers=resolve_value(request_input.headers or {}, context, missing="none"),
            query=resolve_value(request_input.query, context) if request_input.query else None,
            json_body=resolve_value(request_input.json_body, context) if request_input.json_body else None,
            form=resolve_value(request_input.form, context) if request_input.form else None,
        )
    return _build_direct_api_request(request_input, context)


def execute_http_api(api_or_request, context, timeout: int = 30):
    request_data = _normalize_request_payload(api_or_request, context)
    base_url = context.env["baseUrl"].rstrip("/")
    path = request_data.path.lstrip("/")
    url = f"{base_url}/{path}"

    headers = _compact_mapping(request_data.headers)
    params = _compact_mapping(request_data.query) if request_data.query else None
    json_body = request_data.json_body
    form_body = _compact_mapping(request_data.form) if request_data.form else None

    return requests.request(
        method=request_data.method,
        url=url,
        headers=headers,
        params=params,
        json=json_body,
        data=form_body,
        timeout=timeout,
    )
