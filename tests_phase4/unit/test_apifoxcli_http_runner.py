import json

import pytest

from pytest_auto_api2.apifoxcli.assertions import assert_response
from pytest_auto_api2.apifoxcli.context import RunContext
from pytest_auto_api2.apifoxcli.extractor import apply_extractors
from pytest_auto_api2.apifoxcli.models import (
    ApiResource,
    ApiSpec,
    AssertionSpec,
    ExpectSpec,
    ExtractSpec,
    RequestSpec,
)
from pytest_auto_api2.apifoxcli.transport.http import execute_http_api


class DummyResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {"errorCode": 0, "data": {"token": "abc"}}
        self.headers = {"Content-Type": "application/json"}
        self.cookies = {}
        self.text = json.dumps(self._payload)

    def json(self):
        return self._payload


def test_execute_http_api_builds_request(monkeypatch):
    captured = {}

    def fake_request(method, url, headers=None, params=None, json=None, data=None, timeout=30):
        captured.update(
            {
                "method": method,
                "url": url,
                "headers": headers,
                "params": params,
                "json": json,
                "data": data,
            }
        )
        return DummyResponse()

    monkeypatch.setattr("pytest_auto_api2.apifoxcli.transport.http.requests.request", fake_request)

    api = ApiResource(
        kind="api",
        id="login",
        name="Login",
        spec=ApiSpec(
            request=RequestSpec(
                method="POST",
                path="/users/${{userId}}/login",
                headers={"X-Tenant": "${{tenant}}"},
                json={"username": "${{username}}"},
            ),
            expect=ExpectSpec(status=200, assertions=[]),
            extract=[],
        ),
    )
    context = RunContext(
        env={"baseUrl": "http://example.com", "variables": {"tenant": "qa"}},
        dataset={"username": "alice", "userId": "42"},
    )
    response = execute_http_api(api, context)

    assert captured["method"] == "POST"
    assert captured["url"] == "http://example.com/users/42/login"
    assert captured["headers"]["X-Tenant"] == "qa"
    assert captured["json"]["username"] == "alice"
    assert response.status_code == 200


def test_execute_http_api_raises_when_path_placeholder_is_missing():
    api = ApiResource(
        kind="api",
        id="user.detail",
        name="User Detail",
        spec=ApiSpec(
            request=RequestSpec(
                method="GET",
                path="/users/${{userId}}",
            ),
            expect=ExpectSpec(status=200, assertions=[]),
            extract=[],
        ),
    )
    context = RunContext(env={"baseUrl": "http://example.com", "variables": {}}, dataset={})

    with pytest.raises(KeyError, match="userId"):
        execute_http_api(api, context)


def test_execute_http_api_rejects_raw_public_request_path_template():
    api = ApiResource(
        kind="api",
        id="user.detail",
        name="User Detail",
        spec=ApiSpec(
            request=RequestSpec(
                method="GET",
                path="/users/{userId}",
            ),
            expect=ExpectSpec(status=200, assertions=[]),
            extract=[],
        ),
    )
    context = RunContext(env={"baseUrl": "http://example.com", "variables": {}}, dataset={"userId": "42"})

    with pytest.raises(ValueError, match="raw path template"):
        execute_http_api(api, context)


def test_apply_extractors_writes_context_values():
    context = RunContext(env={"baseUrl": "http://example.com", "variables": {}}, dataset={})
    response = DummyResponse(payload={"data": {"token": "abc"}})
    extractors = [ExtractSpec(name="token", expr="$.data.token", **{"from": "response"})]
    apply_extractors(extractors, response, context)
    assert context.values["token"] == "abc"


def test_assert_response_checks_status_and_jsonpath():
    response = DummyResponse(payload={"errorCode": 0})
    expect = ExpectSpec(
        status=200,
        assertions=[
            AssertionSpec(id="errorCode", source="response", expr="$.errorCode", op="==", value=0)
        ],
    )
    assert_response(expect, response, context={})
