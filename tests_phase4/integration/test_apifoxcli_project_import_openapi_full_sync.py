import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from pytest_auto_api2.apifoxcli.cli import main
from pytest_auto_api2.apifoxcli.loader import load_project


class UserByIdHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/users/42":
            self.send_response(404)
            self.end_headers()
            return

        encoded = json.dumps({"code": 200, "userId": "42"}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, *_args):
        return


def _read_summary(capsys):
    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert lines, "expected JSON summary output"
    return json.loads(lines[-1])


def test_project_import_openapi_bootstraps_source_and_full_sync(tmp_path):
    root = tmp_path / "demo"
    assert main(["project", "init", "--project-root", str(root), "--name", "demo-api"]) == 0
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


def test_project_import_openapi_can_api_send_with_resolved_path_placeholder(tmp_path, capsys):
    server = HTTPServer(("127.0.0.1", 0), UserByIdHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        root = tmp_path / "demo"
        assert main(["project", "init", "--project-root", str(root), "--name", "demo-api"]) == 0
        spec = {
            "openapi": "3.0.3",
            "servers": [{"url": f"http://127.0.0.1:{server.server_port}", "description": "qa"}],
            "paths": {
                "/users/{userId}": {
                    "parameters": [
                        {"name": "userId", "in": "path", "required": True, "schema": {"type": "string"}}
                    ],
                    "get": {
                        "operationId": "get_user_by_id",
                        "summary": "Get User By Id",
                        "tags": ["AuthTag"],
                        "responses": {"200": {"description": "ok"}},
                    }
                }
            },
        }
        source_path = tmp_path / "openapi-path.json"
        source_path.write_text(json.dumps(spec), encoding="utf-8")

        assert (
            main(
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
            == 0
        )

        datasets = root / "apifox" / "datasets"
        datasets.mkdir(parents=True, exist_ok=True)
        (datasets / "users.yaml").write_text(
            "kind: dataset\nid: user.rows\nname: users\nspec:\n  rows:\n    - userId: '42'\n",
            encoding="utf-8",
        )

        project = load_project(root)
        api_id = next(
            api.id for api in project.apis.values() if api.spec.request and api.spec.request.path == "/users/${{userId}}"
        )

        exit_code = main(
            ["api", "send", api_id, "--project-root", str(root), "--dataset", "user.rows", "--json"]
        )
        assert exit_code == 0
        summary = _read_summary(capsys)
        assert summary["total"] == 1
        assert summary["details"][0]["request"]["url"].endswith("/users/42")
        assert summary["details"][0]["response"]["status_code"] == 200
    finally:
        server.shutdown()
        thread.join()


def test_project_import_openapi_with_relative_source_can_sync_from_different_cwd(tmp_path, monkeypatch):
    root = tmp_path / "demo"
    assert main(["project", "init", "--project-root", str(root), "--name", "demo-api"]) == 0
    spec = {
        "openapi": "3.0.3",
        "servers": [{"url": "https://demo.example/dev-api", "description": "qa"}],
        "paths": {
            "/login": {
                "post": {
                    "operationId": "login_post",
                    "summary": "Login",
                    "tags": ["登录模块"],
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    }
    source_rel = root / "specs" / "openapi.json"
    source_rel.parent.mkdir(parents=True, exist_ok=True)
    source_rel.write_text(json.dumps(spec), encoding="utf-8")

    monkeypatch.chdir(root)
    exit_code = main(
        [
            "project",
            "import-openapi",
            "--project-root",
            str(root),
            "--source",
            "specs/openapi.json",
            "--source-id",
            "demo-openapi",
            "--server-description",
            "qa",
        ]
    )
    assert exit_code == 0

    source_yaml = (root / "apifox" / "sources" / "demo-openapi.yaml").read_text(encoding="utf-8")
    assert "url: specs/openapi.json" in source_yaml

    monkeypatch.chdir(tmp_path)
    second_exit = main(["source", "sync", "demo-openapi", "--project-root", str(root), "--plan"])
    assert second_exit == 0


def test_project_import_openapi_relative_source_resolves_against_project_root_from_external_cwd(
    tmp_path, monkeypatch
):
    root = tmp_path / "demo"
    assert main(["project", "init", "--project-root", str(root), "--name", "demo-api"]) == 0
    spec = {
        "openapi": "3.0.3",
        "servers": [{"url": "https://demo.example/dev-api", "description": "qa"}],
        "paths": {
            "/login": {
                "post": {
                    "operationId": "login_post",
                    "summary": "Login",
                    "tags": ["登录模块"],
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    }
    source_rel = root / "specs" / "openapi.json"
    source_rel.parent.mkdir(parents=True, exist_ok=True)
    source_rel.write_text(json.dumps(spec), encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    exit_code = main(
        [
            "project",
            "import-openapi",
            "--project-root",
            str(root),
            "--source",
            "specs/openapi.json",
            "--source-id",
            "demo-openapi",
            "--server-description",
            "qa",
        ]
    )

    project = load_project(root)
    source_yaml = (root / "apifox" / "sources" / "demo-openapi.yaml").read_text(encoding="utf-8")
    assert exit_code == 0
    assert "demo-openapi" in project.sources
    assert "auth.post.login" in project.apis
    assert "url: specs/openapi.json" in source_yaml


def test_project_import_openapi_rejects_invalid_source_id_without_partial_persist(tmp_path, capsys):
    root = tmp_path / "demo"
    assert main(["project", "init", "--project-root", str(root), "--name", "demo-api"]) == 0
    spec = {
        "openapi": "3.0.3",
        "servers": [{"url": "https://demo.example/dev-api", "description": "qa"}],
        "paths": {},
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
            "../escaped-source",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "invalid source id" in captured.err
    assert list((root / "apifox" / "sources").glob("*.yaml")) == []


def test_project_import_openapi_rejects_invalid_env_id_without_partial_persist(tmp_path, capsys):
    root = tmp_path / "demo"
    assert main(["project", "init", "--project-root", str(root), "--name", "demo-api"]) == 0
    spec = {
        "openapi": "3.0.3",
        "servers": [{"url": "https://demo.example/dev-api", "description": "qa"}],
        "paths": {},
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
            "--env-id",
            "../escaped-env",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "invalid env id" in captured.err
    assert not (root / "apifox" / "sources" / "demo-openapi.yaml").exists()
