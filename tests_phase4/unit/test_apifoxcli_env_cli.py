import json

import pytest
import yaml

from pytest_auto_api2.apifoxcli.cli import main
from pytest_auto_api2.apifoxcli.loader import load_project
from pytest_auto_api2.apifoxcli.resource_store import env_file


def _read_yaml(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_project_init_writes_named_project_and_default_env(tmp_path):
    root = tmp_path / "demo"

    exit_code = main(
        [
            "project",
            "init",
            "--project-root",
            str(root),
            "--name",
            "demo-api",
            "--default-env",
            "dev",
        ]
    )

    assert exit_code == 0
    assert _read_yaml(root / "apifox" / "project.yaml") == {
        "kind": "project",
        "id": "default",
        "name": "demo-api",
        "spec": {"defaultEnv": "dev"},
    }
    assert _read_yaml(root / "apifox" / "envs" / "dev.yaml") == {
        "kind": "env",
        "id": "dev",
        "name": "dev",
        "spec": {
            "baseUrl": "http://127.0.0.1:8000",
            "headers": {},
            "variables": {},
        },
    }


def test_env_create_and_use_update_canonical_yaml(tmp_path):
    root = tmp_path / "demo"
    assert main(["project", "init", "--project-root", str(root), "--name", "demo-api"]) == 0

    exit_code = main(
        [
            "env",
            "create",
            "dev",
            "--base-url",
            "https://dev.example.com",
            "--project-root",
            str(root),
        ]
    )

    assert exit_code == 0
    assert _read_yaml(root / "apifox" / "envs" / "dev.yaml") == {
        "kind": "env",
        "id": "dev",
        "name": "dev",
        "spec": {
            "baseUrl": "https://dev.example.com",
            "headers": {},
            "variables": {},
        },
    }

    exit_code = main(["env", "use", "dev", "--project-root", str(root)])

    assert exit_code == 0
    assert _read_yaml(root / "apifox" / "project.yaml")["spec"]["defaultEnv"] == "dev"


def test_env_var_and_header_commands_persist_and_round_trip(tmp_path, capsys):
    root = tmp_path / "demo"
    assert main(["project", "init", "--project-root", str(root), "--name", "demo-api"]) == 0
    assert (
        main(
            [
                "env",
                "create",
                "dev",
                "--base-url",
                "https://dev.example.com",
                "--project-root",
                str(root),
            ]
        )
        == 0
    )

    assert main(["env", "var", "set", "dev", "tenant", "blue", "--project-root", str(root)]) == 0
    assert (
        main(
            [
                "env",
                "header",
                "set",
                "dev",
                "Authorization",
                "Bearer ${{token}}",
                "--project-root",
                str(root),
            ]
        )
        == 0
    )
    assert main(["env", "var", "get", "dev", "tenant", "--project-root", str(root)]) == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == "blue"
    assert captured.err == ""

    assert main(["env", "var", "list", "dev", "--project-root", str(root)]) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out.strip()) == {"tenant": "blue"}
    assert captured.err == ""

    project = load_project(root)
    assert project.envs["dev"].spec.variables == {"tenant": "blue"}
    assert project.envs["dev"].spec.headers == {"Authorization": "Bearer ${{token}}"}

    assert main(["env", "var", "unset", "dev", "tenant", "--project-root", str(root)]) == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
    assert load_project(root).envs["dev"].spec.variables == {}


def test_project_reinit_preserves_existing_default_env_configuration(tmp_path):
    root = tmp_path / "demo"
    assert main(["project", "init", "--project-root", str(root), "--name", "demo-api", "--default-env", "dev"]) == 0
    assert (
        main(
            [
                "env",
                "create",
                "dev",
                "--base-url",
                "https://dev.example.com",
                "--project-root",
                str(root),
            ]
        )
        == 0
    )

    exit_code = main(
        [
            "project",
            "init",
            "--project-root",
            str(root),
            "--name",
            "demo-api",
            "--default-env",
            "dev",
        ]
    )

    assert exit_code == 0
    assert _read_yaml(root / "apifox" / "envs" / "dev.yaml")["spec"]["baseUrl"] == "https://dev.example.com"


def test_env_create_fails_before_project_init(tmp_path, capsys):
    root = tmp_path / "demo"

    exit_code = main(
        [
            "env",
            "create",
            "dev",
            "--base-url",
            "https://dev.example.com",
            "--project-root",
            str(root),
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 1
    assert captured.out == ""
    assert "project file not found" in captured.err


def test_project_reinit_updates_scaffold_smoke_env_ref_when_default_env_changes(tmp_path):
    root = tmp_path / "demo"
    assert main(["project", "init", "--project-root", str(root), "--name", "demo-api", "--default-env", "qa"]) == 0
    assert (
        main(
            [
                "env",
                "create",
                "dev",
                "--base-url",
                "https://dev.example.com",
                "--project-root",
                str(root),
            ]
        )
        == 0
    )

    smoke_path = root / "apifox" / "suites" / "smoke.yaml"
    smoke = _read_yaml(smoke_path)
    smoke["spec"]["items"] = [{"apiRef": "auth.health"}]
    smoke_path.write_text(yaml.safe_dump(smoke, allow_unicode=True, sort_keys=False), encoding="utf-8")

    exit_code = main(
        [
            "project",
            "init",
            "--project-root",
            str(root),
            "--name",
            "demo-api",
            "--default-env",
            "dev",
        ]
    )

    updated_smoke = _read_yaml(smoke_path)
    assert exit_code == 0
    assert updated_smoke["spec"]["envRef"] == "dev"
    assert updated_smoke["spec"]["items"] == [{"apiRef": "auth.health"}]


@pytest.mark.parametrize("env_id", ["../escaped-env", "..\\escaped-env", "dev..blue"])
def test_env_file_rejects_invalid_env_ids(tmp_path, env_id):
    with pytest.raises(ValueError, match="invalid env id"):
        env_file(tmp_path, env_id)


@pytest.mark.parametrize("env_id", ["../escaped-env", "..\\escaped-env", "dev..blue"])
def test_env_create_rejects_invalid_env_ids(tmp_path, capsys, env_id):
    root = tmp_path / "demo"
    assert main(["project", "init", "--project-root", str(root), "--name", "demo-api"]) == 0

    exit_code = main(
        [
            "env",
            "create",
            env_id,
            "--base-url",
            "https://dev.example.com",
            "--project-root",
            str(root),
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "invalid env id" in captured.err


@pytest.mark.parametrize("default_env", ["../escaped-env", "..\\escaped-env", "dev..blue"])
def test_project_init_rejects_invalid_default_env_without_partial_persist(tmp_path, capsys, default_env):
    root = tmp_path / "demo"

    exit_code = main(
        [
            "project",
            "init",
            "--project-root",
            str(root),
            "--name",
            "demo-api",
            "--default-env",
            default_env,
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "invalid env id" in captured.err
    assert not (root / "apifox" / "project.yaml").exists()
