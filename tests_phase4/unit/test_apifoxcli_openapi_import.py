import json

import yaml

from pytest_auto_api2.apifoxcli.cli import main
from pytest_auto_api2.apifoxcli.loader import load_project
from pytest_auto_api2.apifoxcli.openapi_importer import import_openapi_project


def test_project_import_openapi_generates_env_and_api_resources(tmp_path):
    root = tmp_path / "demo"
    assert main(["project", "init", "--project-root", str(root), "--name", "demo-api"]) == 0

    spec = {
        "openapi": "3.0.3",
        "servers": [{"url": "https://example.com/dev-api", "description": "qa"}],
        "paths": {
            "/login": {
                "post": {
                    "summary": "Login",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/x-www-form-urlencoded": {
                                "schema": {
                                    "type": "object",
                                    "required": ["username", "password"],
                                    "properties": {
                                        "username": {"type": "string"},
                                        "password": {"type": "string"},
                                        "code": {"type": "string", "default": ""},
                                    },
                                }
                            }
                        },
                    },
                    "responses": {"200": {"description": "ok"}},
                }
            },
            "/users/{userId}": {
                "parameters": [
                    {
                        "name": "userId",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"},
                    }
                ],
                "get": {
                    "summary": "Get User By Id",
                    "responses": {"200": {"description": "ok"}},
                }
            },
            "/getInfo": {
                "get": {
                    "summary": "Get Info",
                    "security": [{"OAuth2PasswordBearer": []}],
                    "responses": {"200": {"description": "ok"}},
                }
            },
        },
    }
    source = tmp_path / "openapi.json"
    source.write_text(json.dumps(spec), encoding="utf-8")

    exit_code = main(
        [
            "project",
            "import-openapi",
            "--project-root",
            str(root),
            "--source",
            str(source),
            "--server-description",
            "qa",
            "--include-path",
            "/login",
            "--include-path",
            "/users/{userId}",
            "--include-path",
            "/getInfo",
        ]
    )
    assert exit_code == 0

    project = load_project(root)
    assert project.envs["qa"].spec.baseUrl == "https://example.com/dev-api"
    assert len(project.apis) == 3

    login_api = next(api for api in project.apis.values() if api.spec.request.path == "/login")
    assert login_api.spec.request.method == "POST"
    assert login_api.spec.request.form == {
        "username": "${{username}}",
        "password": "${{password}}",
        "code": "",
    }

    get_info_api = next(api for api in project.apis.values() if api.spec.request.path == "/getInfo")
    assert get_info_api.spec.request.method == "GET"
    assert get_info_api.spec.expect.status == 200

    get_user_api = next(api for api in project.apis.values() if api.spec.request.path == "/users/${{userId}}")
    assert get_user_api.spec.request.method == "GET"


def test_import_openapi_project_merges_path_item_level_parameters_into_request_path(tmp_path):
    root = tmp_path / "demo"
    spec = {
        "openapi": "3.0.3",
        "servers": [{"url": "https://example.com/dev-api", "description": "qa"}],
        "paths": {
            "/users/{userId}": {
                "parameters": [
                    {
                        "name": "userId",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"},
                    }
                ],
                "get": {
                    "summary": "Get User By Id",
                    "responses": {"200": {"description": "ok"}},
                },
            }
        },
    }
    source = tmp_path / "openapi-direct.json"
    source.write_text(json.dumps(spec), encoding="utf-8")

    assert import_openapi_project(root, str(source), include_paths=["/users/{userId}"]) == 1

    api_files = list((root / "apifox" / "apis").rglob("*.yaml"))
    assert len(api_files) == 1
    payload = yaml.safe_load(api_files[0].read_text(encoding="utf-8"))
    assert payload["spec"]["request"]["path"] == "/users/${{userId}}"
