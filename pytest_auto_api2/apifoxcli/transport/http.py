from __future__ import annotations

import requests

from ..resolver import resolve_value


def execute_http_api(api, context, timeout: int = 30):
    request_spec = api.spec.request
    base_url = context.env["baseUrl"].rstrip("/")
    path = request_spec.path.lstrip("/")
    url = f"{base_url}/{path}"

    headers = resolve_value(request_spec.headers or {}, context)
    params = resolve_value(request_spec.query, context) if request_spec.query else None
    json_body = resolve_value(request_spec.json_body, context) if request_spec.json_body else None
    form_body = resolve_value(request_spec.form, context) if request_spec.form else None

    return requests.request(
        method=request_spec.method,
        url=url,
        headers=headers,
        params=params,
        json=json_body,
        data=form_body,
        timeout=timeout,
    )
