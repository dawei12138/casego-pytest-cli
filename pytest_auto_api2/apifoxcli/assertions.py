from __future__ import annotations

from jsonpath import jsonpath


def assert_response(expect, response, context) -> None:
    assert response.status_code == expect.status, "status code assertion failed"

    payload = response.json()
    for item in expect.assertions:
        if item.source != "response":
            continue
        result = jsonpath(payload, item.expr)
        if result is False:
            raise AssertionError(f"jsonpath not found: {item.expr}")
        actual = result[0] if len(result) == 1 else result
        if item.op == "==":
            assert actual == item.value, f"{item.id} assertion failed"
        else:
            raise AssertionError(f"unsupported assertion op: {item.op}")
