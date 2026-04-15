import pytest

from pytest_auto_api2.apifoxcli.context import RunContext
from pytest_auto_api2.apifoxcli.contract import PreparedRequest, build_case_request, validate_case_contract
from pytest_auto_api2.apifoxcli.models import (
    ApiResource,
    CaseResource,
    EnvResource,
    EnvSpec,
    LoadedProject,
    ProjectResource,
    ProjectSpec,
)
from pytest_auto_api2.apifoxcli.transport.http import execute_http_api
from pytest_auto_api2.apifoxcli.validator import validate_project


class DummyResponse:
    status_code = 200


def test_build_case_request_merges_env_headers_and_case_form():
    api = ApiResource.model_validate(
        {
            "kind": "api",
            "id": "auth.login",
            "name": "login",
            "spec": {
                "protocol": "http",
                "contract": {
                    "request": {
                        "method": "POST",
                        "path": "/login",
                        "contentType": "application/x-www-form-urlencoded",
                        "formSchema": {
                            "username": {"type": "string", "required": True},
                            "password": {"type": "string", "required": True},
                        },
                    },
                    "responses": {"200": {}},
                },
            },
        }
    )
    case = CaseResource.model_validate(
        {
            "kind": "case",
            "id": "auth.login.success",
            "name": "login success",
            "spec": {
                "apiRef": "auth.login",
                "request": {"form": {"username": "${{username}}", "password": "123456"}},
                "expect": {"status": 200, "assertions": []},
                "extract": [],
            },
        }
    )
    context = RunContext(
        env={
            "baseUrl": "https://demo.example/dev-api",
            "headers": {"Authorization": "Bearer ${{token}}"},
            "variables": {},
        },
        dataset={"username": "guest"},
        values={"token": "abc"},
    )

    prepared = build_case_request(case, api, context)
    assert prepared.method == "POST"
    assert prepared.path == "/login"
    assert prepared.headers["Authorization"] == "Bearer abc"
    assert prepared.form == {"username": "guest", "password": "123456"}


def test_build_case_request_prefers_request_snapshot_path_and_resolves_placeholders():
    api = ApiResource.model_validate(
        {
            "kind": "api",
            "id": "auth.profile",
            "name": "profile",
            "spec": {
                "protocol": "http",
                "request": {
                    "method": "GET",
                    "path": "/users/${{userId}}/profile",
                },
                "contract": {
                    "request": {
                        "method": "GET",
                        "path": "/users/{userId}/profile",
                    },
                    "responses": {"200": {}},
                },
            },
        }
    )
    case = CaseResource.model_validate(
        {
            "kind": "case",
            "id": "auth.profile.smoke",
            "name": "profile smoke",
            "spec": {
                "apiRef": "auth.profile",
                "request": {},
                "expect": {"status": 200, "assertions": []},
                "extract": [],
            },
        }
    )
    context = RunContext(
        env={"baseUrl": "https://demo.example/dev-api", "headers": {}, "variables": {}},
        dataset={"userId": "42"},
    )

    prepared = build_case_request(case, api, context)

    assert prepared.method == "GET"
    assert prepared.path == "/users/42/profile"


def test_build_case_request_raises_when_path_placeholder_is_missing():
    api = ApiResource.model_validate(
        {
            "kind": "api",
            "id": "auth.profile",
            "name": "profile",
            "spec": {
                "protocol": "http",
                "request": {
                    "method": "GET",
                    "path": "/users/${{userId}}/profile",
                },
                "contract": {
                    "request": {
                        "method": "GET",
                        "path": "/users/{userId}/profile",
                    },
                    "responses": {"200": {}},
                },
            },
        }
    )
    case = CaseResource.model_validate(
        {
            "kind": "case",
            "id": "auth.profile.smoke",
            "name": "profile smoke",
            "spec": {
                "apiRef": "auth.profile",
                "request": {},
                "expect": {"status": 200, "assertions": []},
                "extract": [],
            },
        }
    )
    context = RunContext(
        env={"baseUrl": "https://demo.example/dev-api", "headers": {}, "variables": {}},
        dataset={},
    )

    with pytest.raises(KeyError, match="userId"):
        build_case_request(case, api, context)


@pytest.mark.parametrize(
    ("request_contract", "missing_field", "message_match"),
    [
        ({"path": "/login"}, "method", "method.*auth\\.login\\.missing-contract.*auth\\.login"),
        ({"method": "POST"}, "path", "path.*auth\\.login\\.missing-contract.*auth\\.login"),
    ],
)
def test_build_case_request_raises_clear_error_when_contract_missing_method_or_path(
    request_contract, missing_field, message_match
):
    api = ApiResource.model_validate(
        {
            "kind": "api",
            "id": "auth.login",
            "name": "login",
            "spec": {
                "protocol": "http",
                "contract": {
                    "request": request_contract,
                    "responses": {"200": {}},
                },
            },
        }
    )
    case = CaseResource.model_validate(
        {
            "kind": "case",
            "id": "auth.login.missing-contract",
            "name": "login missing contract",
            "spec": {
                "apiRef": "auth.login",
                "request": {"form": {"username": "guest"}},
                "expect": {"status": 200, "assertions": []},
                "extract": [],
            },
        }
    )
    context = RunContext(
        env={"baseUrl": "https://demo.example/dev-api", "headers": {}, "variables": {}},
        dataset={},
    )

    with pytest.raises(ValueError, match=message_match):
        build_case_request(case, api, context)


def test_validate_case_contract_reports_missing_required_input():
    api = ApiResource.model_validate(
        {
            "kind": "api",
            "id": "auth.login",
            "name": "login",
            "spec": {
                "protocol": "http",
                "contract": {
                    "request": {
                        "method": "POST",
                        "path": "/login",
                        "contentType": "application/x-www-form-urlencoded",
                        "formSchema": {
                            "username": {"type": "string", "required": True},
                            "password": {"type": "string", "required": True},
                        },
                    },
                    "responses": {"200": {}},
                },
            },
        }
    )
    case = CaseResource.model_validate(
        {
            "kind": "case",
            "id": "auth.login.invalid",
            "name": "login invalid",
            "spec": {
                "apiRef": "auth.login",
                "request": {"form": {"username": "guest"}},
                "expect": {"status": 200, "assertions": []},
                "extract": [],
            },
        }
    )

    errors = validate_case_contract(case, api)
    assert errors == ["missing required form field: password"]


def test_execute_http_api_raises_clear_error_without_request_data_for_direct_api():
    api = ApiResource.model_validate(
        {
            "kind": "api",
            "id": "auth.login",
            "name": "login",
            "spec": {
                "protocol": "http",
                "contract": {
                    "request": {"method": "POST", "path": "/login"},
                    "responses": {"200": {}},
                },
            },
        }
    )
    context = RunContext(
        env={"baseUrl": "https://demo.example/dev-api", "headers": {}, "variables": {}},
        dataset={},
    )

    with pytest.raises(ValueError, match="missing request data"):
        execute_http_api(api, context)


def test_execute_http_api_supports_prepared_request_payload(monkeypatch):
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
                "timeout": timeout,
            }
        )
        return DummyResponse()

    monkeypatch.setattr("pytest_auto_api2.apifoxcli.transport.http.requests.request", fake_request)

    context = RunContext(
        env={"baseUrl": "https://demo.example/dev-api", "headers": {}, "variables": {}},
        dataset={"userId": "42"},
        values={"token": "abc"},
    )
    request_data = PreparedRequest(
        method="POST",
        path="/users/${{userId}}/login",
        headers={"Authorization": "Bearer ${{token}}"},
        query={"tenant": "qa"},
        json_body={"username": "guest"},
        form={"password": "123456"},
    )

    response = execute_http_api(request_data, context)

    assert captured == {
        "method": "POST",
        "url": "https://demo.example/dev-api/users/42/login",
        "headers": {"Authorization": "Bearer abc"},
        "params": {"tenant": "qa"},
        "json": {"username": "guest"},
        "data": {"password": "123456"},
        "timeout": 30,
    }
    assert response.status_code == 200


def test_validate_project_checks_case_request_expressions(tmp_path):
    project = LoadedProject(
        root=tmp_path,
        project=ProjectResource(
            kind="project",
            id="default",
            name="demo",
            spec=ProjectSpec(defaultEnv="qa"),
        ),
        envs={
            "qa": EnvResource(
                kind="env",
                id="qa",
                name="qa",
                spec=EnvSpec(baseUrl="https://demo.example/dev-api", headers={}, variables={}),
            )
        },
        apis={
            "auth.login": ApiResource.model_validate(
                {
                    "kind": "api",
                    "id": "auth.login",
                    "name": "login",
                    "spec": {
                        "protocol": "http",
                        "contract": {"request": {"method": "POST", "path": "/login"}},
                    },
                }
            )
        },
        cases={
            "auth.login.case": CaseResource.model_validate(
                {
                    "kind": "case",
                    "id": "auth.login.case",
                    "name": "login case",
                    "spec": {
                        "apiRef": "auth.login",
                        "request": {"headers": {"Authorization": "Bearer ${bad.token}"}},
                        "expect": {"status": 200, "assertions": []},
                        "extract": [],
                    },
                }
            )
        },
    )

    errors = validate_project(project)
    assert any("bad.token" in item for item in errors)
