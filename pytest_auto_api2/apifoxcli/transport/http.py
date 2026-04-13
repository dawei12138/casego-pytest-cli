from __future__ import annotations

import requests

from ..resolver import resolve_value


def _compact_mapping(value):
    if not value:
        return None
    return {key: item for key, item in value.items() if item not in (None, "")} or None


def execute_http_api(api, context, timeout: int = 30):
    request_spec = api.spec.request
    base_url = context.env["baseUrl"].rstrip("/")
    path = request_spec.path.lstrip("/")
    url = f"{base_url}/{path}"

    raw_headers = {}
    raw_headers.update(context.env.get("headers") or {})
    raw_headers.update(request_spec.headers or {})

    headers = _compact_mapping(resolve_value(raw_headers, context, missing="none"))
    params = _compact_mapping(resolve_value(request_spec.query, context)) if request_spec.query else None
    json_body = resolve_value(request_spec.json_body, context) if request_spec.json_body else None
    form_body = _compact_mapping(resolve_value(request_spec.form, context)) if request_spec.form else None

    return requests.request(
        method=request_spec.method,
        url=url,
        headers=headers,
        params=params,
        json=json_body,
        data=form_body,
        timeout=timeout,
    )
