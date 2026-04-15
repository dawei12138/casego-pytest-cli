from pathlib import Path

import yaml

from pytest_auto_api2.apifoxcli.cli import main
from pytest_auto_api2.apifoxcli.loader import load_project
from pytest_auto_api2.apifoxcli.validator import validate_project


def _resource_file(root: Path, collection: str, resource_id: str) -> Path:
    return (root / "apifox" / collection).joinpath(*resource_id.split(".")).with_suffix(".yaml")


def _write_yaml(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _write_api(root: Path, payload) -> None:
    _write_yaml(_resource_file(root, "apis", payload["id"]), payload)


def _read_single_case_payload(root: Path):
    case_files = list((root / "apifox" / "cases").rglob("*.yaml"))
    assert len(case_files) == 1
    return yaml.safe_load(case_files[0].read_text(encoding="utf-8"))


def test_case_create_from_api_copies_request_snapshot(tmp_path):
    root = tmp_path / "demo"
    assert main(["project", "init", "--project-root", str(root), "--name", "demo-api"]) == 0
    _write_api(
        root,
        {
            "kind": "api",
            "id": "auth.profile",
            "name": "profile",
                "spec": {
                    "protocol": "http",
                    "envRef": "qa",
                    "request": {
                    "method": "POST",
                    "path": "/users/${{userId}}/profile",
                    "headers": {
                        "Content-Type": "application/json",
                        "X-Tenant": "${{tenant}}",
                    },
                        "query": {"verbose": "${{verbose}}"},
                        "json": {"nickname": "${{nickname}}"},
                    },
                    "expect": {
                        "status": 201,
                        "assertions": [
                            {
                                "id": "keep-me",
                                "source": "response",
                                "expr": "$.status",
                                "op": "==",
                                "value": "created",
                            }
                        ],
                    },
                    "extract": [{"name": "token", "from": "response", "expr": "$.token"}],
                },
            },
        )

    exit_code = main(
        [
            "case",
            "create",
            "auth.profile.saved",
            "--from-api",
            "auth.profile",
            "--project-root",
            str(root),
        ]
    )

    payload = _read_single_case_payload(root)

    assert exit_code == 0
    assert payload["kind"] == "case"
    assert payload["id"] == "auth.profile.saved"
    assert payload["name"]
    assert payload["spec"]["apiRef"] == "auth.profile"
    assert payload["spec"]["data"] == {}
    assert payload["spec"]["request"] == {
        "method": "POST",
        "path": "/users/${{userId}}/profile",
        "headers": {
            "Content-Type": "application/json",
            "X-Tenant": "${{tenant}}",
        },
        "query": {"verbose": "${{verbose}}"},
        "json": {"nickname": "${{nickname}}"},
    }
    assert payload["spec"]["expect"] == {"status": 200, "assertions": []}
    assert payload["spec"]["extract"] == []
    assert payload["spec"]["hooks"] == {"before": [], "after": []}


def test_case_create_from_api_loader_reads_placeholder_snapshot(tmp_path):
    root = tmp_path / "demo"
    assert main(["project", "init", "--project-root", str(root), "--name", "demo-api"]) == 0
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
                    "headers": {"X-Trace-Id": "${{traceId}}"},
                    "query": {"tenant": "${{tenant}}"},
                    "json": {"name": "${{name}}"},
                },
                "expect": {"status": 200, "assertions": []},
                "extract": [],
            },
        },
    )

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
    case = project.cases["sales.create-order.smoke"]

    assert case.spec.request == {
        "method": "POST",
        "path": "/orders/${{orderId}}",
        "headers": {"X-Trace-Id": "${{traceId}}"},
        "query": {"tenant": "${{tenant}}"},
        "json": {"name": "${{name}}"},
    }
    assert validate_project(project) == []


def test_case_create_from_api_uses_empty_request_when_api_has_no_snapshot(tmp_path):
    root = tmp_path / "demo"
    assert main(["project", "init", "--project-root", str(root), "--name", "demo-api"]) == 0
    _write_api(
        root,
        {
            "kind": "api",
            "id": "auth.contract-only",
            "name": "contract only",
            "spec": {
                "protocol": "http",
                "envRef": "qa",
                "contract": {
                    "request": {"method": "GET", "path": "/contract-only"},
                    "responses": {"200": {}},
                },
                "expect": {"status": 200, "assertions": []},
                "extract": [],
            },
        },
    )

    assert (
        main(
            [
                "case",
                "create",
                "auth.contract-only.smoke",
                "--from-api",
                "auth.contract-only",
                "--project-root",
                str(root),
            ]
        )
        == 0
    )

    project = load_project(root)
    assert project.cases["auth.contract-only.smoke"].spec.request == {}
