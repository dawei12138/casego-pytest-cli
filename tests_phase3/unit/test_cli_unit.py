#!/usr/bin/env python
# -*- coding: utf-8 -*-

import importlib
import sys
from pathlib import Path

from pytest_auto_api2 import cli


def test_parser_commands_are_registered():
    parser = cli._build_parser()

    args_gen = parser.parse_args(["gen"])
    assert args_gen.command == "gen"
    assert args_gen.func.__name__ == "_cmd_gen"

    args_run = parser.parse_args(["run"])
    assert args_run.command == "run"
    assert args_run.func.__name__ == "_cmd_run"

    args_all = parser.parse_args(["all"])
    assert args_all.command == "all"
    assert args_all.func.__name__ == "_cmd_all"

    args_ini = parser.parse_args(["ini"])
    assert args_ini.command == "ini"
    assert args_ini.func.__name__ == "_cmd_init"

    args_validate = parser.parse_args(["validate"])
    assert args_validate.command == "validate"
    assert args_validate.func.__name__ == "_cmd_validate"


def test_prepare_project_sets_runtime_env(tmp_path, monkeypatch):
    project_root = tmp_path / "demo"
    (project_root / "common").mkdir(parents=True)
    (project_root / "cases").mkdir(parents=True)
    (project_root / "tests_out").mkdir(parents=True)
    (project_root / "conf").mkdir(parents=True)

    config_path = project_root / "conf" / "qa.yaml"
    config_path.write_text("project_name: demo\n", encoding="utf-8")

    monkeypatch.delenv("PYTEST_AUTO_API2_HOME", raising=False)
    monkeypatch.delenv("PYTEST_AUTO_API2_CONFIG", raising=False)
    monkeypatch.delenv("PYTEST_AUTO_API2_DATA_DIR", raising=False)
    monkeypatch.delenv("PYTEST_AUTO_API2_TEST_DIR", raising=False)

    project = cli._prepare_project(
        project_root=str(project_root),
        config="conf/qa.yaml",
        data_dir="cases",
        test_dir="tests_out",
        require_config=True,
        require_data=True,
        require_test=True,
    )

    assert project["root"] == project_root.resolve()
    assert project["config"] == config_path.resolve()
    assert project["data"] == (project_root / "cases").resolve()
    assert project["test"] == (project_root / "tests_out").resolve()

    assert Path(cli.os.environ["PYTEST_AUTO_API2_HOME"]) == project_root.resolve()
    assert Path(cli.os.environ["PYTEST_AUTO_API2_CONFIG"]) == config_path.resolve()
    assert Path(cli.os.environ["PYTEST_AUTO_API2_DATA_DIR"]) == (project_root / "cases").resolve()
    assert Path(cli.os.environ["PYTEST_AUTO_API2_TEST_DIR"]) == (project_root / "tests_out").resolve()


def test_build_pytest_args_respects_options(tmp_path):
    parser = cli._build_parser()
    args = parser.parse_args(
        [
            "run",
            "--keyword",
            "smoke_case",
            "--marker",
            "smoke",
            "--maxfail",
            "2",
            "--allure",
            "--clean-allure",
            "custom_target.py",
        ]
    )
    project = {
        "root": tmp_path,
        "config": tmp_path / "common" / "config.yaml",
        "data": tmp_path / "data",
        "test": tmp_path / "test_case",
    }

    pytest_args = cli._build_pytest_args(args, project)

    assert "-s" in pytest_args
    assert pytest_args[pytest_args.index("-k") + 1] == "smoke_case"
    assert pytest_args[pytest_args.index("-m") + 1] == "smoke"
    assert pytest_args[pytest_args.index("--maxfail") + 1] == "2"
    assert "--alluredir" in pytest_args
    assert "--clean-alluredir" in pytest_args
    assert "custom_target.py" in pytest_args


def test_build_pytest_args_json_mode_uses_quiet(tmp_path):
    parser = cli._build_parser()
    args = parser.parse_args(["run", "--json"])
    project = {
        "root": tmp_path,
        "config": tmp_path / "common" / "config.yaml",
        "data": tmp_path / "data",
        "test": tmp_path / "test_case",
    }
    pytest_args = cli._build_pytest_args(args, project)
    assert "-q" in pytest_args


def test_runtime_imports_are_isolated_from_shadowed_top_level_packages(tmp_path, monkeypatch):
    repo_root = Path(__file__).resolve().parents[2]
    monkeypatch.setenv("PYTEST_AUTO_API2_HOME", str(repo_root))
    monkeypatch.setenv("PYTEST_AUTO_API2_CONFIG", str(repo_root / "common" / "config.yaml"))
    monkeypatch.setenv("PYTEST_AUTO_API2_DATA_DIR", str(repo_root / "data"))
    monkeypatch.setenv("PYTEST_AUTO_API2_TEST_DIR", str(repo_root / "test_case"))

    shadow_root = tmp_path / "shadow"
    (shadow_root / "utils").mkdir(parents=True)
    (shadow_root / "utils" / "__init__.py").write_text("# shadow utils\n", encoding="utf-8")
    (shadow_root / "common").mkdir(parents=True)
    (shadow_root / "common" / "__init__.py").write_text("# shadow common\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(shadow_root))

    for module_name in (
        "common",
        "utils",
        "pytest_auto_api2.runtime.loader",
        "pytest_auto_api2.runtime.api",
    ):
        sys.modules.pop(module_name, None)

    loader_mod = importlib.import_module("pytest_auto_api2.runtime.loader")
    api_mod = importlib.import_module("pytest_auto_api2.runtime.api")

    assert hasattr(loader_mod, "build_case_cache")
    assert hasattr(api_mod, "RequestControl")


def test_gen_and_all_force_flags_are_available():
    parser = cli._build_parser()

    args_gen = parser.parse_args(["gen", "--force"])
    assert args_gen.command == "gen"
    assert args_gen.force is True

    args_all = parser.parse_args(["all", "--force-gen"])
    assert args_all.command == "all"
    assert args_all.force_gen is True
