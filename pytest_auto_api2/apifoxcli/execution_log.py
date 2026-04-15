from __future__ import annotations

import json
from typing import Any, Dict

from pytest_auto_api2.utils.logging_tool.log_control import ERROR, INFO


def _stringify(value: Any) -> str:
    if value is None:
        return "None"
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False)
    except TypeError:
        return str(value)


def _request_payload(detail: Dict[str, Any]) -> Any:
    request = detail.get("request") or {}
    for key in ("json", "form", "query"):
        value = request.get(key)
        if value not in (None, {}, []):
            return value
    return None


def emit_execution_log(detail: Dict[str, Any]) -> None:
    request = detail.get("request") or {}
    response = detail.get("response") or {}
    title = detail.get("title") or detail.get("resource_id") or "<unknown>"
    url = request.get("url")
    method = request.get("method")
    headers = request.get("headers")
    response_body = response.get("body")
    elapsed_ms = detail.get("elapsed_ms")
    status_code = detail.get("status_code") or response.get("status_code")
    error = detail.get("error")

    log_message = (
        "\n======================================================\n"
        f"用例标题: {title}\n"
        f"请求路径: {url}\n"
        f"请求方式: {method}\n"
        f"请求头:   {_stringify(headers)}\n"
        f"请求内容: {_stringify(_request_payload(detail))}\n"
        f"接口响应内容: {_stringify(response_body)}\n"
        f"接口响应时长: {elapsed_ms} ms\n"
        f"Http状态码: {status_code}\n"
        f"执行结果: {'FAIL' if error else 'PASS'}\n"
        f"执行错误: {error or 'None'}\n"
        "====================================================="
    )

    if error or (status_code is not None and int(status_code) >= 400):
        ERROR.logger.error(log_message)
    else:
        INFO.logger.info(log_message)
