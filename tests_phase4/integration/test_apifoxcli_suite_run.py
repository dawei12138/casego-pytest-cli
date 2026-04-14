import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from pytest_auto_api2.apifoxcli.cli import main


class DemoHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"])).decode("utf-8")
        payload = json.loads(body)
        response = {"errorCode": 0, "data": {"username": payload["username"]}}
        encoded = json.dumps(response).encode("utf-8")
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


def test_suite_run_executes_canonical_yaml(tmp_path, capsys):
    server = HTTPServer(("127.0.0.1", 0), DemoHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        root = tmp_path
        apifox = root / "apifox"
        for rel in ("envs", "apis", "cases", "datasets", "suites"):
            (apifox / rel).mkdir(parents=True, exist_ok=True)

        (apifox / "project.yaml").write_text(
            "kind: project\nid: default\nname: demo\nspec:\n  defaultEnv: qa\n",
            encoding="utf-8",
        )
        (apifox / "envs" / "qa.yaml").write_text(
            f"kind: env\nid: qa\nname: qa\nspec:\n  baseUrl: http://127.0.0.1:{server.server_port}\n  variables: {{}}\n",
            encoding="utf-8",
        )
        (apifox / "apis" / "login.yaml").write_text(
            "kind: api\nid: user.login\nname: login\nspec:\n  protocol: http\n  envRef: qa\n  contract:\n    request:\n      method: POST\n      path: /login\n      contentType: application/json\n      bodySchema:\n        type: object\n        required:\n          - username\n    responses:\n      '200': {}\n",
            encoding="utf-8",
        )
        (apifox / "cases" / "login.yaml").write_text(
            "kind: case\nid: user.login.smoke\nname: login smoke\nspec:\n  apiRef: user.login\n  envRef: qa\n  request:\n    json:\n      username: ${dataset.username}\n  expect:\n    status: 200\n    assertions:\n      - id: errorCode\n        source: response\n        expr: $.errorCode\n        op: ==\n        value: 0\n      - id: username\n        source: response\n        expr: $.data.username\n        op: ==\n        value: alice\n  extract: []\n",
            encoding="utf-8",
        )
        (apifox / "datasets" / "users.yaml").write_text(
            "kind: dataset\nid: user.rows\nname: users\nspec:\n  rows:\n    - username: alice\n",
            encoding="utf-8",
        )
        (apifox / "suites" / "smoke.yaml").write_text(
            "kind: suite\nid: smoke\nname: smoke\nspec:\n  envRef: qa\n  failFast: true\n  concurrency: 1\n  items:\n    - caseRef: user.login.smoke\n      datasetRef: user.rows\n",
            encoding="utf-8",
        )

        exit_code = main(["suite", "run", "smoke", "--project-root", str(root), "--json"])
        assert exit_code == 0
        summary = _read_summary(capsys)
        assert summary["total"] == 1
        assert [item["resource_id"] for item in summary["details"]] == ["user.login.smoke"]
    finally:
        server.shutdown()
        thread.join()
