import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs

from pytest_auto_api2.apifoxcli.cli import main


class AuthChainHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/login":
            self.send_response(404)
            self.end_headers()
            return

        body = self.rfile.read(int(self.headers["Content-Length"])).decode("utf-8")
        form = parse_qs(body)
        username = form["username"][0]
        response = {"code": 200, "token": f"token-{username}"}
        encoded = json.dumps(response).encode("utf-8")
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


def _write_auth_chain_project(root, port):
    apifox = root / "apifox"
    for rel in ("envs", "apis", "flows", "suites", "datasets"):
        (apifox / rel).mkdir(parents=True, exist_ok=True)

    (apifox / "project.yaml").write_text(
        "kind: project\nid: default\nname: demo\nspec:\n  defaultEnv: qa\n",
        encoding="utf-8",
    )
    (apifox / "envs" / "qa.yaml").write_text(
        f"kind: env\nid: qa\nname: qa\nspec:\n  baseUrl: http://127.0.0.1:{port}\n  headers:\n    Authorization: Bearer ${{context.token}}\n  variables: {{}}\n",
        encoding="utf-8",
    )
    (apifox / "apis" / "login.yaml").write_text(
        "kind: api\nid: auth.login\nname: login\nspec:\n  protocol: http\n  envRef: qa\n  request:\n    method: POST\n    path: /login\n    headers:\n      Content-Type: application/x-www-form-urlencoded\n    form:\n      username: ${dataset.username}\n      password: ${dataset.password}\n  expect:\n    status: 200\n    assertions:\n      - id: login-code\n        source: response\n        expr: $.code\n        op: ==\n        value: 200\n  extract:\n    - name: token\n      from: response\n      expr: $.token\n",
        encoding="utf-8",
    )
    (apifox / "apis" / "get-info.yaml").write_text(
        "kind: api\nid: auth.get-info\nname: get info\nspec:\n  protocol: http\n  envRef: qa\n  request:\n    method: GET\n    path: /getInfo\n  expect:\n    status: 200\n    assertions:\n      - id: user-name\n        source: response\n        expr: $.user.userName\n        op: ==\n        value: alice\n",
        encoding="utf-8",
    )
    (apifox / "flows" / "bootstrap.yaml").write_text(
        "kind: flow\nid: auth.bootstrap\nname: bootstrap\nspec:\n  envRef: qa\n  steps:\n    - apiRef: auth.login\n    - apiRef: auth.get-info\n",
        encoding="utf-8",
    )
    (apifox / "datasets" / "users.yaml").write_text(
        "kind: dataset\nid: auth.users\nname: users\nspec:\n  rows:\n    - username: alice\n      password: secret\n",
        encoding="utf-8",
    )
    (apifox / "suites" / "smoke.yaml").write_text(
        "kind: suite\nid: smoke\nname: smoke\nspec:\n  envRef: qa\n  failFast: true\n  concurrency: 1\n  items:\n    - flowRef: auth.bootstrap\n      datasetRef: auth.users\n",
        encoding="utf-8",
    )


def test_flow_run_executes_with_dataset_and_env_headers(tmp_path):
    server = HTTPServer(("127.0.0.1", 0), AuthChainHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        _write_auth_chain_project(tmp_path, server.server_port)
        exit_code = main(
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
        )
        assert exit_code == 0
    finally:
        server.shutdown()
        thread.join()


def test_suite_run_executes_flow_with_extracted_token_and_env_headers(tmp_path):
    server = HTTPServer(("127.0.0.1", 0), AuthChainHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        _write_auth_chain_project(tmp_path, server.server_port)
        exit_code = main(["suite", "run", "smoke", "--project-root", str(tmp_path), "--json"])
        assert exit_code == 0
    finally:
        server.shutdown()
        thread.join()
