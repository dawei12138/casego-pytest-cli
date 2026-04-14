from pytest_auto_api2.apifoxcli.context import RunContext
from pytest_auto_api2.apifoxcli.contract import build_case_request, validate_case_contract
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
                "request": {"form": {"username": "${dataset.username}", "password": "123456"}},
                "expect": {"status": 200, "assertions": []},
                "extract": [],
            },
        }
    )
    context = RunContext(
        env={
            "baseUrl": "https://demo.example/dev-api",
            "headers": {"Authorization": "Bearer ${context.token}"},
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

    try:
        execute_http_api(api, context)
    except (ValueError, AssertionError) as exc:
        assert "request" in str(exc).lower()
        assert "missing" in str(exc).lower()
    else:
        raise AssertionError("expected clear missing request data error")


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
