import json

from pytest_auto_api2.apifoxcli.cli import main
from pytest_auto_api2.apifoxcli.loader import load_project


def test_project_import_openapi_generates_env_and_api_resources(tmp_path):
    root = tmp_path / "demo"
    assert main(["project", "init", "--project-root", str(root)]) == 0

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
            "/getInfo",
        ]
    )
    assert exit_code == 0

    project = load_project(root)
    assert project.envs["qa"].spec.baseUrl == "https://example.com/dev-api"
    assert len(project.apis) == 2

    login_api = next(api for api in project.apis.values() if api.spec.request.path == "/login")
    assert login_api.spec.request.method == "POST"
    assert login_api.spec.request.form == {
        "username": "${dataset.username}",
        "password": "${dataset.password}",
        "code": "",
    }

    get_info_api = next(api for api in project.apis.values() if api.spec.request.path == "/getInfo")
    assert get_info_api.spec.request.method == "GET"
    assert get_info_api.spec.expect.status == 200
