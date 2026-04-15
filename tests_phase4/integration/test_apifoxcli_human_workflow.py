import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import yaml

from pytest_auto_api2.apifoxcli.cli import main
from pytest_auto_api2.apifoxcli.loader import load_project


class SaveCaseWorkflowHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        parsed = urlparse(self.path)
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])).decode("utf-8"))
        response_body = {"ok": True}

        if (
            parsed.path != "/orders/A-42"
            or parse_qs(parsed.query) != {"tenant": ["blue"]}
            or self.headers.get("X-Trace-Id") != "trace-123"
            or body != {"name": "Widget"}
        ):
            response_body = {
                "ok": False,
                "path": parsed.path,
                "query": parse_qs(parsed.query),
                "traceId": self.headers.get("X-Trace-Id"),
                "body": body,
            }
            encoded = json.dumps(response_body).encode("utf-8")
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
            return

        encoded = json.dumps(response_body).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, *_args):
        return


def _write_yaml(path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _write_api(root, payload) -> None:
    path = (root / "apifox" / "apis").joinpath(*payload["id"].split(".")).with_suffix(".yaml")
    _write_yaml(path, payload)


def _write_dataset(root, payload) -> None:
    path = (root / "apifox" / "datasets").joinpath(*payload["id"].split(".")).with_suffix(".yaml")
    _write_yaml(path, payload)


def _read_summary(capsys):
    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert lines, "expected JSON summary output"
    return json.loads(lines[-1])


def test_human_workflow_api_send_then_save_as_case_then_case_send(tmp_path, capsys):
    server = HTTPServer(("127.0.0.1", 0), SaveCaseWorkflowHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        root = tmp_path / "demo"
        assert main(["project", "init", "--project-root", str(root), "--name", "demo-api"]) == 0
        assert (
            main(
                [
                    "env",
                    "create",
                    "qa",
                    "--base-url",
                    f"http://127.0.0.1:{server.server_port}",
                    "--project-root",
                    str(root),
                ]
            )
            == 0
        )
        _write_api(
            root,
            {
                "kind": "api",
                "id": "sales.create-order",
                "name": "create order",
                "spec": {
                    "protocol": "http",
                    "envRef": "qa",
                    "request": {
                        "method": "POST",
                        "path": "/orders/${{orderId}}",
                        "headers": {
                            "Content-Type": "application/json",
                            "X-Trace-Id": "${{traceId}}",
                        },
                        "query": {"tenant": "${{tenant}}"},
                        "json": {"name": "${{name}}"},
                    },
                    "expect": {"status": 200, "assertions": []},
                    "extract": [],
                },
            },
        )
        _write_dataset(
            root,
            {
                "kind": "dataset",
                "id": "sales.order-inputs",
                "name": "order inputs",
                "spec": {
                    "rows": [
                        {
                            "orderId": "A-42",
                            "traceId": "trace-123",
                            "tenant": "blue",
                            "name": "Widget",
                        }
                    ]
                },
            },
        )

        assert (
            main(
                [
                    "api",
                    "send",
                    "sales.create-order",
                    "--project-root",
                    str(root),
                    "--dataset",
                    "sales.order-inputs",
                    "--json",
                ]
            )
            == 0
        )
        api_summary = _read_summary(capsys)
        assert api_summary["details"][0]["request"]["url"] == f"http://127.0.0.1:{server.server_port}/orders/A-42"
        assert api_summary["details"][0]["request"]["query"] == {"tenant": "blue"}
        assert api_summary["details"][0]["request"]["json"] == {"name": "Widget"}

        assert (
            main(
                [
                    "case",
                    "create",
                    "sales.create-order.smoke",
                    "--from-api",
                    "sales.create-order",
                    "--project-root",
                    str(root),
                ]
            )
            == 0
        )

        project = load_project(root)
        assert project.cases["sales.create-order.smoke"].spec.request["path"] == "/orders/${{orderId}}"

        assert (
            main(
                [
                    "case",
                    "send",
                    "sales.create-order.smoke",
                    "--project-root",
                    str(root),
                    "--dataset",
                    "sales.order-inputs",
                    "--json",
                ]
            )
            == 0
        )
        case_summary = _read_summary(capsys)

        assert case_summary["details"][0]["resource_id"] == "sales.create-order.smoke"
        assert case_summary["details"][0]["request"]["url"] == f"http://127.0.0.1:{server.server_port}/orders/A-42"
        assert case_summary["details"][0]["request"]["headers"]["X-Trace-Id"] == "trace-123"
        assert case_summary["details"][0]["request"]["query"] == {"tenant": "blue"}
        assert case_summary["details"][0]["request"]["json"] == {"name": "Widget"}
        assert case_summary["details"][0]["status_code"] == 200
    finally:
        server.shutdown()
        thread.join()


def test_human_workflow_flow_and_suite_create_then_run(tmp_path, capsys):
    server = HTTPServer(("127.0.0.1", 0), SaveCaseWorkflowHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        root = tmp_path / "demo"
        api_id = "sales.create-order"
        case_id = "sales.create-order.smoke"
        flow_id = "sales.order-flow"
        suite_id = "sales.smoke"
        dataset_id = "sales.order-inputs"

        assert main(["project", "init", "--project-root", str(root), "--name", "demo-api"]) == 0
        assert (
            main(
                [
                    "env",
                    "create",
                    "qa",
                    "--base-url",
                    f"http://127.0.0.1:{server.server_port}",
                    "--project-root",
                    str(root),
                ]
            )
            == 0
        )
        _write_api(
            root,
            {
                "kind": "api",
                "id": api_id,
                "name": "create order",
                "spec": {
                    "protocol": "http",
                    "envRef": "qa",
                    "request": {
                        "method": "POST",
                        "path": "/orders/${{orderId}}",
                        "headers": {
                            "Content-Type": "application/json",
                            "X-Trace-Id": "${{traceId}}",
                        },
                        "query": {"tenant": "${{tenant}}"},
                        "json": {"name": "${{name}}"},
                    },
                    "expect": {"status": 200, "assertions": []},
                    "extract": [],
                },
            },
        )
        _write_dataset(
            root,
            {
                "kind": "dataset",
                "id": dataset_id,
                "name": "order inputs",
                "spec": {
                    "rows": [
                        {
                            "orderId": "A-42",
                            "traceId": "trace-123",
                            "tenant": "blue",
                            "name": "Widget",
                        }
                    ]
                },
            },
        )

        assert (
            main(
                [
                    "case",
                    "create",
                    case_id,
                    "--from-api",
                    api_id,
                    "--project-root",
                    str(root),
                ]
            )
            == 0
        )
        assert main(["flow", "create", flow_id, "--project-root", str(root)]) == 0
        assert (
            main(
                [
                    "flow",
                    "add",
                    flow_id,
                    "--case",
                    case_id,
                    "--project-root",
                    str(root),
                ]
            )
            == 0
        )
        assert (
            main(
                [
                    "flow",
                    "add",
                    flow_id,
                    "--api",
                    api_id,
                    "--project-root",
                    str(root),
                ]
            )
            == 0
        )
        assert main(["suite", "create", suite_id, "--project-root", str(root)]) == 0
        assert (
            main(
                [
                    "suite",
                    "add",
                    suite_id,
                    "--flow",
                    flow_id,
                    "--dataset",
                    dataset_id,
                    "--project-root",
                    str(root),
                ]
            )
            == 0
        )
        assert (
            main(
                [
                    "suite",
                    "add",
                    suite_id,
                    "--case",
                    case_id,
                    "--dataset",
                    dataset_id,
                    "--project-root",
                    str(root),
                ]
            )
            == 0
        )

        project = load_project(root)
        assert [step.caseRef or step.apiRef for step in project.flows[flow_id].spec.steps] == [case_id, api_id]
        assert [item.flowRef or item.caseRef for item in project.suites[suite_id].spec.items] == [flow_id, case_id]

        assert main(["suite", "run", suite_id, "--project-root", str(root), "--json"]) == 0
        suite_summary = _read_summary(capsys)

        assert suite_summary["total"] == 3
        assert [item["resource_id"] for item in suite_summary["details"]] == [case_id, api_id, case_id]
        assert all(item["status_code"] == 200 for item in suite_summary["details"])
    finally:
        server.shutdown()
        thread.join()
