import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs

import pytest

from pytest_auto_api2.apifoxcli.cli import main
from pytest_auto_api2.apifoxcli.loader import load_project
from pytest_auto_api2.apifoxcli.planner import build_flow_plan, build_suite_plan
from pytest_auto_api2.apifoxcli.validator import validate_project


class DemoHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"])).decode("utf-8")
        form = parse_qs(body)
        encoded = json.dumps({"code": 200, "token": f"token-{form['username'][0]}"}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self):
        encoded = json.dumps({"code": 200, "user": {"userName": "alice"}}).encode("utf-8")
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


def test_case_flow_and_suite_run_use_case_refs(tmp_path, capsys):
    server = HTTPServer(("127.0.0.1", 0), DemoHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        apifox = tmp_path / "apifox"
        for rel in ("envs", "apis", "cases", "flows", "suites", "datasets"):
            (apifox / rel).mkdir(parents=True, exist_ok=True)

        (apifox / "project.yaml").write_text(
            "kind: project\nid: default\nname: demo\nspec:\n  defaultEnv: qa\n",
            encoding="utf-8",
        )
        (apifox / "envs" / "qa.yaml").write_text(
            f"kind: env\nid: qa\nname: QA\nspec:\n  baseUrl: http://127.0.0.1:{server.server_port}\n  headers:\n    Authorization: Bearer ${{{{token}}}}\n  variables: {{}}\n",
            encoding="utf-8",
        )
        (apifox / "apis" / "auth-login.yaml").write_text(
            "kind: api\nid: auth.login\nname: login\nspec:\n  protocol: http\n  contract:\n    request:\n      method: POST\n      path: /login\n      contentType: application/x-www-form-urlencoded\n      formSchema:\n        username:\n          type: string\n          required: true\n        password:\n          type: string\n          required: true\n    responses:\n      '200': {}\n",
            encoding="utf-8",
        )
        (apifox / "apis" / "auth-get-info.yaml").write_text(
            "kind: api\nid: auth.get-info\nname: get info\nspec:\n  protocol: http\n  contract:\n    request:\n      method: GET\n      path: /getInfo\n      contentType: application/json\n    responses:\n      '200': {}\n",
            encoding="utf-8",
        )
        (apifox / "cases" / "login-success.yaml").write_text(
            "kind: case\nid: auth.login.success\nname: login success\nspec:\n  apiRef: auth.login\n  request:\n    form:\n      username: ${{username}}\n      password: ${{password}}\n  expect:\n    status: 200\n    assertions:\n      - id: login-code\n        source: response\n        expr: $.code\n        op: ==\n        value: 200\n  extract:\n    - name: token\n      from: response\n      expr: $.token\n",
            encoding="utf-8",
        )
        (apifox / "cases" / "get-info.yaml").write_text(
            "kind: case\nid: auth.get-info.smoke\nname: get info\nspec:\n  apiRef: auth.get-info\n  request: {}\n  expect:\n    status: 200\n    assertions:\n      - id: user-name\n        source: response\n        expr: $.user.userName\n        op: ==\n        value: alice\n  extract: []\n",
            encoding="utf-8",
        )
        (apifox / "flows" / "bootstrap.yaml").write_text(
            "kind: flow\nid: auth.bootstrap\nname: bootstrap\nspec:\n  steps:\n    - caseRef: auth.login.success\n    - caseRef: auth.get-info.smoke\n",
            encoding="utf-8",
        )
        (apifox / "datasets" / "users.yaml").write_text(
            "kind: dataset\nid: auth.users\nname: users\nspec:\n  rows:\n    - username: alice\n      password: secret\n",
            encoding="utf-8",
        )
        (apifox / "suites" / "smoke.yaml").write_text(
            "kind: suite\nid: smoke\nname: smoke\nspec:\n  failFast: true\n  concurrency: 1\n  items:\n    - caseRef: auth.login.success\n      datasetRef: auth.users\n    - flowRef: auth.bootstrap\n      datasetRef: auth.users\n",
            encoding="utf-8",
        )

        assert main(
            [
                "case",
                "run",
                "auth.login.success",
                "--project-root",
                str(tmp_path),
                "--dataset",
                "auth.users",
                "--json",
            ]
        ) == 0
        case_summary = _read_summary(capsys)
        assert case_summary["total"] == 1
        assert [item["resource_id"] for item in case_summary["details"]] == ["auth.login.success"]

        assert main(
            [
                "flow",
                "run",
                "auth.bootstrap",
                "--project-root",
                str(tmp_path),
                "--dataset",
                "auth.users",
                "--json",
            ]
        ) == 0
        flow_summary = _read_summary(capsys)
        assert flow_summary["total"] == 2
        assert [item["resource_id"] for item in flow_summary["details"]] == [
            "auth.login.success",
            "auth.get-info.smoke",
        ]

        assert main(["suite", "run", "smoke", "--project-root", str(tmp_path), "--json"]) == 0
        suite_summary = _read_summary(capsys)
        assert suite_summary["total"] == 3
        assert [item["resource_id"] for item in suite_summary["details"]] == [
            "auth.login.success",
            "auth.login.success",
            "auth.get-info.smoke",
        ]
    finally:
        server.shutdown()
        thread.join()


def test_validate_flow_step_requires_exactly_one_reference(tmp_path):
    apifox = tmp_path / "apifox"
    for rel in ("envs", "apis", "cases", "flows"):
        (apifox / rel).mkdir(parents=True, exist_ok=True)

    (apifox / "project.yaml").write_text(
        "kind: project\nid: default\nname: demo\nspec:\n  defaultEnv: qa\n",
        encoding="utf-8",
    )
    (apifox / "envs" / "qa.yaml").write_text(
        "kind: env\nid: qa\nname: qa\nspec:\n  baseUrl: http://example.com\n  variables: {}\n",
        encoding="utf-8",
    )
    (apifox / "apis" / "login.yaml").write_text(
        "kind: api\nid: auth.login\nname: login\nspec:\n  protocol: http\n  contract:\n    request:\n      method: POST\n      path: /login\n    responses:\n      '200': {}\n",
        encoding="utf-8",
    )
    (apifox / "cases" / "login.yaml").write_text(
        "kind: case\nid: auth.login.success\nname: login\nspec:\n  apiRef: auth.login\n  request: {}\n  expect:\n    status: 200\n    assertions: []\n  extract: []\n",
        encoding="utf-8",
    )
    (apifox / "flows" / "broken.yaml").write_text(
        "kind: flow\nid: auth.broken\nname: broken\nspec:\n  steps:\n    - caseRef: auth.login.success\n      apiRef: auth.login\n    - {}\n",
        encoding="utf-8",
    )

    project = load_project(tmp_path)
    errors = validate_project(project)
    assert any("flow auth.broken step 0 must define exactly one of caseRef or apiRef" in item for item in errors)
    assert any("flow auth.broken step 1 must define exactly one of caseRef or apiRef" in item for item in errors)


def test_validate_suite_item_requires_exactly_one_reference(tmp_path):
    apifox = tmp_path / "apifox"
    for rel in ("envs", "apis", "cases", "flows", "suites"):
        (apifox / rel).mkdir(parents=True, exist_ok=True)

    (apifox / "project.yaml").write_text(
        "kind: project\nid: default\nname: demo\nspec:\n  defaultEnv: qa\n",
        encoding="utf-8",
    )
    (apifox / "envs" / "qa.yaml").write_text(
        "kind: env\nid: qa\nname: qa\nspec:\n  baseUrl: http://example.com\n  variables: {}\n",
        encoding="utf-8",
    )
    (apifox / "apis" / "login.yaml").write_text(
        "kind: api\nid: auth.login\nname: login\nspec:\n  protocol: http\n  contract:\n    request:\n      method: POST\n      path: /login\n    responses:\n      '200': {}\n",
        encoding="utf-8",
    )
    (apifox / "cases" / "login.yaml").write_text(
        "kind: case\nid: auth.login.success\nname: login\nspec:\n  apiRef: auth.login\n  request: {}\n  expect:\n    status: 200\n    assertions: []\n  extract: []\n",
        encoding="utf-8",
    )
    (apifox / "flows" / "bootstrap.yaml").write_text(
        "kind: flow\nid: auth.bootstrap\nname: bootstrap\nspec:\n  steps:\n    - caseRef: auth.login.success\n",
        encoding="utf-8",
    )
    (apifox / "suites" / "broken.yaml").write_text(
        "kind: suite\nid: broken\nname: broken\nspec:\n  items:\n    - caseRef: auth.login.success\n      apiRef: auth.login\n    - flowRef: auth.bootstrap\n      caseRef: auth.login.success\n    - {}\n",
        encoding="utf-8",
    )

    project = load_project(tmp_path)
    errors = validate_project(project)
    assert any(
        "suite broken item 0 must define exactly one of caseRef, apiRef, or flowRef" in item for item in errors
    )
    assert any(
        "suite broken item 1 must define exactly one of caseRef, apiRef, or flowRef" in item for item in errors
    )
    assert any(
        "suite broken item 2 must define exactly one of caseRef, apiRef, or flowRef" in item for item in errors
    )


def test_flow_run_with_invalid_step_fails_in_planner(tmp_path):
    apifox = tmp_path / "apifox"
    for rel in ("envs", "flows"):
        (apifox / rel).mkdir(parents=True, exist_ok=True)

    (apifox / "project.yaml").write_text(
        "kind: project\nid: default\nname: demo\nspec:\n  defaultEnv: qa\n",
        encoding="utf-8",
    )
    (apifox / "envs" / "qa.yaml").write_text(
        "kind: env\nid: qa\nname: qa\nspec:\n  baseUrl: http://example.com\n  variables: {}\n",
        encoding="utf-8",
    )
    (apifox / "flows" / "broken.yaml").write_text(
        "kind: flow\nid: broken\nname: broken\nspec:\n  steps:\n    - {}\n",
        encoding="utf-8",
    )

    assert main(["flow", "run", "broken", "--project-root", str(tmp_path), "--json"]) == 1

    project = load_project(tmp_path)
    with pytest.raises(ValueError, match="flow broken step 0 must define exactly one of caseRef or apiRef"):
        build_flow_plan(project, "broken", None)


def test_suite_run_with_invalid_item_fails_in_planner(tmp_path):
    apifox = tmp_path / "apifox"
    for rel in ("envs", "suites"):
        (apifox / rel).mkdir(parents=True, exist_ok=True)

    (apifox / "project.yaml").write_text(
        "kind: project\nid: default\nname: demo\nspec:\n  defaultEnv: qa\n",
        encoding="utf-8",
    )
    (apifox / "envs" / "qa.yaml").write_text(
        "kind: env\nid: qa\nname: qa\nspec:\n  baseUrl: http://example.com\n  variables: {}\n",
        encoding="utf-8",
    )
    (apifox / "suites" / "broken.yaml").write_text(
        "kind: suite\nid: broken\nname: broken\nspec:\n  items:\n    - {}\n",
        encoding="utf-8",
    )

    assert main(["suite", "run", "broken", "--project-root", str(tmp_path), "--json"]) == 1

    project = load_project(tmp_path)
    with pytest.raises(
        ValueError, match="suite broken item 0 must define exactly one of caseRef, apiRef, or flowRef"
    ):
        build_suite_plan(project, "broken", None)


class LegacyApiRefHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/login":
            self.send_response(404)
            self.end_headers()
            return

        body = self.rfile.read(int(self.headers["Content-Length"])).decode("utf-8")
        payload = json.loads(body)
        encoded = json.dumps({"code": 200, "token": f"token-{payload['username']}"}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self):
        if self.path != "/getInfo":
            self.send_response(404)
            self.end_headers()
            return

        auth = self.headers.get("Authorization")
        if auth != "Bearer token-alice":
            self.send_response(401)
            self.end_headers()
            return
        encoded = json.dumps({"code": 200, "user": {"userName": "alice"}}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, *_args):
        return


def test_flow_and_suite_support_legacy_api_refs(tmp_path, capsys):
    server = HTTPServer(("127.0.0.1", 0), LegacyApiRefHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        apifox = tmp_path / "apifox"
        for rel in ("envs", "apis", "flows", "suites", "datasets"):
            (apifox / rel).mkdir(parents=True, exist_ok=True)

        (apifox / "project.yaml").write_text(
            "kind: project\nid: default\nname: demo\nspec:\n  defaultEnv: qa\n",
            encoding="utf-8",
        )
        (apifox / "envs" / "qa.yaml").write_text(
            f"kind: env\nid: qa\nname: qa\nspec:\n  baseUrl: http://127.0.0.1:{server.server_port}\n  headers:\n    Authorization: Bearer ${{{{token}}}}\n  variables: {{}}\n",
            encoding="utf-8",
        )
        (apifox / "apis" / "login.yaml").write_text(
            "kind: api\nid: auth.login\nname: login\nspec:\n  protocol: http\n  envRef: qa\n  request:\n    method: POST\n    path: /login\n    headers:\n      Content-Type: application/json\n    json:\n      username: ${{username}}\n  expect:\n    status: 200\n    assertions:\n      - id: login-code\n        source: response\n        expr: $.code\n        op: ==\n        value: 200\n  extract:\n    - name: token\n      from: response\n      expr: $.token\n",
            encoding="utf-8",
        )
        (apifox / "apis" / "get-info.yaml").write_text(
            "kind: api\nid: auth.get-info\nname: get info\nspec:\n  protocol: http\n  envRef: qa\n  request:\n    method: GET\n    path: /getInfo\n  expect:\n    status: 200\n    assertions:\n      - id: user-name\n        source: response\n        expr: $.user.userName\n        op: ==\n        value: alice\n  extract: []\n",
            encoding="utf-8",
        )
        (apifox / "flows" / "legacy.yaml").write_text(
            "kind: flow\nid: auth.legacy\nname: legacy\nspec:\n  steps:\n    - apiRef: auth.login\n    - apiRef: auth.get-info\n",
            encoding="utf-8",
        )
        (apifox / "datasets" / "users.yaml").write_text(
            "kind: dataset\nid: auth.users\nname: users\nspec:\n  rows:\n    - username: alice\n",
            encoding="utf-8",
        )
        (apifox / "suites" / "legacy.yaml").write_text(
            "kind: suite\nid: legacy\nname: legacy\nspec:\n  items:\n    - apiRef: auth.login\n      datasetRef: auth.users\n    - flowRef: auth.legacy\n      datasetRef: auth.users\n",
            encoding="utf-8",
        )

        assert main(
            [
                "flow",
                "run",
                "auth.legacy",
                "--project-root",
                str(tmp_path),
                "--dataset",
                "auth.users",
                "--json",
            ]
        ) == 0
        flow_summary = _read_summary(capsys)
        assert flow_summary["total"] == 2
        assert [item["resource_id"] for item in flow_summary["details"]] == ["auth.login", "auth.get-info"]

        assert main(["suite", "run", "legacy", "--project-root", str(tmp_path), "--json"]) == 0
        suite_summary = _read_summary(capsys)
        assert suite_summary["total"] == 3
        assert [item["resource_id"] for item in suite_summary["details"]] == [
            "auth.login",
            "auth.login",
            "auth.get-info",
        ]
    finally:
        server.shutdown()
        thread.join()
