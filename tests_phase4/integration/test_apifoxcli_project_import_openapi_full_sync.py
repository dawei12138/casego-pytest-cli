import json

from pytest_auto_api2.apifoxcli.cli import main
from pytest_auto_api2.apifoxcli.loader import load_project


def test_project_import_openapi_bootstraps_source_and_full_sync(tmp_path):
    root = tmp_path / "demo"
    assert main(["project", "init", "--project-root", str(root)]) == 0
    spec = {
        "openapi": "3.0.3",
        "servers": [{"url": "https://demo.example/dev-api", "description": "qa"}],
        "paths": {
            "/login": {
                "post": {
                    "operationId": "login_post",
                    "summary": "Login",
                    "tags": ["登录模块"],
                    "requestBody": {
                        "content": {
                            "application/x-www-form-urlencoded": {
                                "schema": {
                                    "type": "object",
                                    "required": ["username", "password"],
                                    "properties": {
                                        "username": {"type": "string"},
                                        "password": {"type": "string"},
                                    },
                                }
                            }
                        }
                    },
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    }
    source_path = tmp_path / "openapi.json"
    source_path.write_text(json.dumps(spec), encoding="utf-8")

    exit_code = main(
        [
            "project",
            "import-openapi",
            "--project-root",
            str(root),
            "--source",
            str(source_path),
            "--source-id",
            "demo-openapi",
            "--server-description",
            "qa",
        ]
    )

    project = load_project(root)
    assert exit_code == 0
    assert "demo-openapi" in project.sources
    assert "auth.post.login" in project.apis
