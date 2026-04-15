from pathlib import Path

import pytest
import yaml

from pytest_auto_api2.apifoxcli.cli import build_parser, main
from pytest_auto_api2.apifoxcli.loader import load_project
from pytest_auto_api2.apifoxcli.resource_store import (
    append_flow_step,
    append_suite_item,
    resource_file,
)
from pytest_auto_api2.apifoxcli.validator import validate_project


def _resource_file(root: Path, collection: str, resource_id: str) -> Path:
    return (root / "apifox" / collection).joinpath(*resource_id.split(".")).with_suffix(".yaml")


def _write_yaml(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _read_yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _write_api(root: Path, payload) -> None:
    _write_yaml(_resource_file(root, "apis", payload["id"]), payload)


def _write_case(root: Path, payload) -> None:
    _write_yaml(_resource_file(root, "cases", payload["id"]), payload)


def _write_dataset(root: Path, payload) -> None:
    _write_yaml(_resource_file(root, "datasets", payload["id"]), payload)


def _write_flow(root: Path, payload) -> None:
    _write_yaml(_resource_file(root, "flows", payload["id"]), payload)


def _write_suite(root: Path, payload) -> None:
    _write_yaml(_resource_file(root, "suites", payload["id"]), payload)


def test_flow_create_and_add_case_refs_persist_yaml(tmp_path):
    root = tmp_path / "demo"
    assert main(["project", "init", "--project-root", str(root), "--name", "demo-api"]) == 0
    _write_api(
        root,
        {
            "kind": "api",
            "id": "auth.login",
            "name": "login",
            "spec": {
                "protocol": "http",
                "envRef": "qa",
                "request": {"method": "POST", "path": "/login"},
                "expect": {"status": 200, "assertions": []},
                "extract": [],
            },
        },
    )
    _write_case(
        root,
        {
            "kind": "case",
            "id": "auth.login.smoke",
            "name": "login smoke",
            "spec": {
                "apiRef": "auth.login",
                "request": {},
                "expect": {"status": 200, "assertions": []},
                "extract": [],
            },
        },
    )
    _write_case(
        root,
        {
            "kind": "case",
            "id": "auth.login.admin",
            "name": "login admin",
            "spec": {
                "apiRef": "auth.login",
                "request": {},
                "expect": {"status": 200, "assertions": []},
                "extract": [],
            },
        },
    )

    assert main(["flow", "create", "auth.bootstrap", "--project-root", str(root)]) == 0
    assert (
        main(
            [
                "flow",
                "add",
                "auth.bootstrap",
                "--case",
                "auth.login.smoke",
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
                "auth.bootstrap",
                "--case",
                "auth.login.admin",
                "--project-root",
                str(root),
            ]
        )
        == 0
    )

    payload = _read_yaml(_resource_file(root, "flows", "auth.bootstrap"))
    project = load_project(root)

    assert payload == {
        "kind": "flow",
        "id": "auth.bootstrap",
        "name": "auth.bootstrap",
        "spec": {
            "steps": [
                {"caseRef": "auth.login.smoke"},
                {"caseRef": "auth.login.admin"},
            ]
        },
    }
    assert project.flows["auth.bootstrap"].spec.steps[0].caseRef == "auth.login.smoke"
    assert validate_project(project) == []


def test_flow_add_api_ref_persists_yaml(tmp_path):
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
                "request": {"method": "GET", "path": "/profile"},
                "expect": {"status": 200, "assertions": []},
                "extract": [],
            },
        },
    )

    assert main(["flow", "create", "auth.profile-flow", "--project-root", str(root)]) == 0
    assert (
        main(
            [
                "flow",
                "add",
                "auth.profile-flow",
                "--api",
                "auth.profile",
                "--project-root",
                str(root),
            ]
        )
        == 0
    )

    payload = _read_yaml(_resource_file(root, "flows", "auth.profile-flow"))
    project = load_project(root)

    assert payload == {
        "kind": "flow",
        "id": "auth.profile-flow",
        "name": "auth.profile-flow",
        "spec": {"steps": [{"apiRef": "auth.profile"}]},
    }
    assert project.flows["auth.profile-flow"].spec.steps[0].apiRef == "auth.profile"
    assert validate_project(project) == []


def test_suite_create_and_add_flow_ref_persist_yaml(tmp_path):
    root = tmp_path / "demo"
    assert main(["project", "init", "--project-root", str(root), "--name", "demo-api"]) == 0
    assert main(["flow", "create", "auth.bootstrap", "--project-root", str(root)]) == 0

    assert main(["suite", "create", "smoke.custom", "--project-root", str(root)]) == 0
    assert (
        main(
            [
                "suite",
                "add",
                "smoke.custom",
                "--flow",
                "auth.bootstrap",
                "--project-root",
                str(root),
            ]
        )
        == 0
    )

    payload = _read_yaml(_resource_file(root, "suites", "smoke.custom"))
    project = load_project(root)

    assert payload == {
        "kind": "suite",
        "id": "smoke.custom",
        "name": "smoke.custom",
        "spec": {"items": [{"flowRef": "auth.bootstrap"}]},
    }
    assert project.suites["smoke.custom"].spec.items[0].flowRef == "auth.bootstrap"
    assert validate_project(project) == []


def test_suite_add_case_or_api_with_dataset_ref_persists_yaml(tmp_path):
    root = tmp_path / "demo"
    assert main(["project", "init", "--project-root", str(root), "--name", "demo-api"]) == 0
    _write_api(
        root,
        {
            "kind": "api",
            "id": "auth.login",
            "name": "login",
            "spec": {
                "protocol": "http",
                "envRef": "qa",
                "request": {"method": "POST", "path": "/login"},
                "expect": {"status": 200, "assertions": []},
                "extract": [],
            },
        },
    )
    _write_case(
        root,
        {
            "kind": "case",
            "id": "auth.login.smoke",
            "name": "login smoke",
            "spec": {
                "apiRef": "auth.login",
                "request": {},
                "expect": {"status": 200, "assertions": []},
                "extract": [],
            },
        },
    )
    _write_dataset(
        root,
        {
            "kind": "dataset",
            "id": "auth.users",
            "name": "users",
            "spec": {"rows": [{"username": "alice"}]},
        },
    )

    assert main(["suite", "create", "auth.smoke", "--project-root", str(root)]) == 0
    assert (
        main(
            [
                "suite",
                "add",
                "auth.smoke",
                "--case",
                "auth.login.smoke",
                "--dataset",
                "auth.users",
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
                "auth.smoke",
                "--api",
                "auth.login",
                "--dataset",
                "auth.users",
                "--project-root",
                str(root),
            ]
        )
        == 0
    )

    payload = _read_yaml(_resource_file(root, "suites", "auth.smoke"))
    project = load_project(root)

    assert payload == {
        "kind": "suite",
        "id": "auth.smoke",
        "name": "auth.smoke",
        "spec": {
            "items": [
                {"caseRef": "auth.login.smoke", "datasetRef": "auth.users"},
                {"apiRef": "auth.login", "datasetRef": "auth.users"},
            ]
        },
    }
    assert project.suites["auth.smoke"].spec.items[0].datasetRef == "auth.users"
    assert validate_project(project) == []


def test_build_parser_rejects_invalid_flow_add_reference_selection():
    parser = build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["flow", "add", "auth.bootstrap"])

    with pytest.raises(SystemExit):
        parser.parse_args(["flow", "add", "auth.bootstrap", "--case", "auth.login.smoke", "--api", "auth.login"])


def test_build_parser_rejects_invalid_suite_add_reference_selection():
    parser = build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["suite", "add", "auth.smoke"])

    with pytest.raises(SystemExit):
        parser.parse_args(
            ["suite", "add", "auth.smoke", "--case", "auth.login.smoke", "--flow", "auth.bootstrap"]
        )


@pytest.mark.parametrize(
    ("argv", "expected_error"),
    [
        (
            ["flow", "add", "auth.missing", "--case", "auth.login.smoke"],
            "flow not found: auth.missing",
        ),
        (
            ["suite", "add", "auth.missing", "--flow", "auth.bootstrap"],
            "suite not found: auth.missing",
        ),
    ],
)
def test_flow_and_suite_add_fail_when_target_missing(tmp_path, capsys, argv, expected_error):
    root = tmp_path / "demo"
    assert main(["project", "init", "--project-root", str(root), "--name", "demo-api"]) == 0

    exit_code = main([*argv, "--project-root", str(root)])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert captured.out == ""
    assert expected_error in captured.err


@pytest.mark.parametrize(
    ("argv", "expected_error"),
    [
        (
            ["flow", "add", "auth.bootstrap", "--case", "auth.login.smoke"],
            "case not found: auth.login.smoke",
        ),
        (
            ["flow", "add", "auth.bootstrap", "--api", "auth.login"],
            "api not found: auth.login",
        ),
        (
            ["suite", "add", "auth.smoke", "--case", "auth.login.smoke"],
            "case not found: auth.login.smoke",
        ),
        (
            ["suite", "add", "auth.smoke", "--api", "auth.login"],
            "api not found: auth.login",
        ),
        (
            ["suite", "add", "auth.smoke", "--flow", "auth.missing"],
            "flow not found: auth.missing",
        ),
        (
            ["suite", "add", "auth.smoke", "--case", "auth.login.smoke", "--dataset", "auth.users"],
            "case not found: auth.login.smoke",
        ),
    ],
)
def test_flow_and_suite_add_fail_when_reference_missing(tmp_path, capsys, argv, expected_error):
    root = tmp_path / "demo"
    assert main(["project", "init", "--project-root", str(root), "--name", "demo-api"]) == 0
    assert main(["flow", "create", "auth.bootstrap", "--project-root", str(root)]) == 0
    assert main(["suite", "create", "auth.smoke", "--project-root", str(root)]) == 0

    exit_code = main([*argv, "--project-root", str(root)])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert captured.out == ""
    assert expected_error in captured.err


def test_suite_add_fails_when_dataset_missing_for_existing_reference(tmp_path, capsys):
    root = tmp_path / "demo"
    assert main(["project", "init", "--project-root", str(root), "--name", "demo-api"]) == 0
    _write_api(
        root,
        {
            "kind": "api",
            "id": "auth.login",
            "name": "login",
            "spec": {
                "protocol": "http",
                "envRef": "qa",
                "request": {"method": "POST", "path": "/login"},
                "expect": {"status": 200, "assertions": []},
                "extract": [],
            },
        },
    )
    _write_case(
        root,
        {
            "kind": "case",
            "id": "auth.login.smoke",
            "name": "login smoke",
            "spec": {
                "apiRef": "auth.login",
                "request": {},
                "expect": {"status": 200, "assertions": []},
                "extract": [],
            },
        },
    )
    assert main(["suite", "create", "auth.smoke", "--project-root", str(root)]) == 0

    exit_code = main(
        [
            "suite",
            "add",
            "auth.smoke",
            "--case",
            "auth.login.smoke",
            "--dataset",
            "auth.users",
            "--project-root",
            str(root),
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 1
    assert captured.out == ""
    assert "dataset not found: auth.users" in captured.err


@pytest.mark.parametrize(
    ("writer", "append_call", "resource_id", "payload_spec", "expected_error"),
    [
        (
            _write_flow,
            lambda root, resource_id: append_flow_step(root, resource_id, case_ref="auth.login.smoke"),
            "auth.invalid-flow",
            "invalid",
            "resource spec must be a mapping",
        ),
        (
            _write_suite,
            lambda root, resource_id: append_suite_item(root, resource_id, case_ref="auth.login.smoke"),
            "auth.invalid-suite",
            "invalid",
            "resource spec must be a mapping",
        ),
        (
            _write_flow,
            lambda root, resource_id: append_flow_step(root, resource_id, case_ref="auth.login.smoke"),
            "auth.invalid-flow-steps",
            {"steps": ""},
            "resource spec.steps must be a list",
        ),
        (
            _write_suite,
            lambda root, resource_id: append_suite_item(root, resource_id, case_ref="auth.login.smoke"),
            "auth.invalid-suite-items",
            {"items": ""},
            "resource spec.items must be a list",
        ),
    ],
)
def test_append_operations_fail_fast_on_invalid_existing_structure(
    tmp_path, writer, append_call, resource_id, payload_spec, expected_error
):
    root = tmp_path / "demo"
    assert main(["project", "init", "--project-root", str(root), "--name", "demo-api"]) == 0
    resource_path = _resource_file(root, "flows" if "flow" in resource_id else "suites", resource_id)
    writer(
        root,
        {
            "kind": "flow" if "flow" in resource_id else "suite",
            "id": resource_id,
            "name": resource_id,
            "spec": payload_spec,
        },
    )

    with pytest.raises(TypeError, match=expected_error):
        append_call(root, resource_id)

    assert _read_yaml(resource_path)["spec"] == payload_spec


@pytest.mark.parametrize(
    ("argv", "collection", "resource_id"),
    [
        (["flow", "create", "auth.bootstrap"], "flows", "auth.bootstrap"),
        (["suite", "create", "auth.smoke"], "suites", "auth.smoke"),
    ],
)
def test_create_commands_do_not_require_loading_unrelated_invalid_resources(tmp_path, argv, collection, resource_id):
    root = tmp_path / "demo"
    assert main(["project", "init", "--project-root", str(root), "--name", "demo-api"]) == 0
    _write_api(
        root,
        {
            "kind": "api",
            "id": "broken.shape",
            "name": "broken shape",
            "spec": "invalid",
        },
    )

    assert main([*argv, "--project-root", str(root)]) == 0

    payload = _read_yaml(_resource_file(root, collection, resource_id))
    assert payload["id"] == resource_id


@pytest.mark.parametrize(
    ("setup_target", "argv", "collection", "resource_id"),
    [
        (
            lambda root: _write_flow(
                root,
                {
                    "kind": "flow",
                    "id": "auth.bootstrap",
                    "name": "auth.bootstrap",
                    "spec": {"steps": []},
                },
            ),
            ["flow", "add", "auth.bootstrap", "--case", "auth.login.smoke"],
            "flows",
            "auth.bootstrap",
        ),
        (
            lambda root: _write_suite(
                root,
                {
                    "kind": "suite",
                    "id": "auth.smoke",
                    "name": "auth.smoke",
                    "spec": {"items": []},
                },
            ),
            ["suite", "add", "auth.smoke", "--case", "auth.login.smoke"],
            "suites",
            "auth.smoke",
        ),
    ],
)
def test_add_commands_do_not_require_loading_unrelated_invalid_resources(
    tmp_path, setup_target, argv, collection, resource_id
):
    root = tmp_path / "demo"
    assert main(["project", "init", "--project-root", str(root), "--name", "demo-api"]) == 0
    _write_api(
        root,
        {
            "kind": "api",
            "id": "broken.shape",
            "name": "broken shape",
            "spec": "invalid",
        },
    )
    _write_case(
        root,
        {
            "kind": "case",
            "id": "auth.login.smoke",
            "name": "login smoke",
            "spec": {
                "apiRef": "auth.login",
                "request": {},
                "expect": {"status": 200, "assertions": []},
                "extract": [],
            },
        },
    )
    setup_target(root)

    assert main([*argv, "--project-root", str(root)]) == 0

    payload = _read_yaml(_resource_file(root, collection, resource_id))
    items = payload["spec"]["steps"] if collection == "flows" else payload["spec"]["items"]
    assert items == [{"caseRef": "auth.login.smoke"}]


@pytest.mark.parametrize("resource_id", ["../outside", "..\\outside", "auth..escape"])
def test_resource_file_rejects_invalid_resource_ids(tmp_path, resource_id):
    with pytest.raises(ValueError, match="invalid resource id"):
        resource_file(tmp_path, "flows", resource_id)


@pytest.mark.parametrize(
    "argv",
    [
        ["flow", "create", "../outside"],
        ["suite", "create", "..\\outside"],
    ],
)
def test_create_commands_reject_invalid_resource_ids(tmp_path, capsys, argv):
    root = tmp_path / "demo"
    assert main(["project", "init", "--project-root", str(root), "--name", "demo-api"]) == 0

    exit_code = main([*argv, "--project-root", str(root)])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "invalid resource id" in captured.err
