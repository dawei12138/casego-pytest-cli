#!/usr/bin/env python
# -*- coding: utf-8 -*-

import json
import os
import subprocess
import sys


def _run_cli(*args, cwd=None):
    cmd = [sys.executable, "-m", "pytest_auto_api2.cli", *args]
    env = os.environ.copy()
    env.pop("PYTEST_AUTO_API2_HOME", None)
    env.pop("PYTEST_AUTO_API2_CONFIG", None)
    env.pop("PYTEST_AUTO_API2_DATA_DIR", None)
    env.pop("PYTEST_AUTO_API2_TEST_DIR", None)
    return subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)


def _last_nonempty_line(text: str) -> str:
    lines = [line for line in text.splitlines() if line.strip()]
    return lines[-1] if lines else ""


def test_init_and_gen_generate_namespaced_test(tmp_path):
    project_dir = tmp_path / "demo_project"
    init_res = _run_cli("init", str(project_dir))
    assert init_res.returncode == 0, init_res.stderr

    gen_res = _run_cli("gen", "--project-root", str(project_dir))
    assert gen_res.returncode == 0, gen_res.stderr

    generated_file = project_dir / "test_case" / "test_demo_banner.py"
    assert generated_file.exists()
    content = generated_file.read_text(encoding="utf-8")
    assert "from pytest_auto_api2.runtime.api import" in content
    assert "from pytest_auto_api2.runtime.loader import" in content


def test_gen_and_run_with_custom_data_and_test_dir(tmp_path):
    project_dir = tmp_path / "custom_project"
    init_res = _run_cli("init", str(project_dir))
    assert init_res.returncode == 0, init_res.stderr

    custom_data = project_dir / "custom_cases"
    custom_data.mkdir(parents=True, exist_ok=True)
    (custom_data / "demo_banner.yaml").write_text(
        (project_dir / "data" / "demo_banner.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    custom_tests = project_dir / "generated_tests"
    gen_res = _run_cli(
        "gen",
        "--project-root",
        str(project_dir),
        "--data-dir",
        "custom_cases",
        "--test-dir",
        "generated_tests",
    )
    assert gen_res.returncode == 0, gen_res.stderr
    assert (custom_tests / "test_demo_banner.py").exists()

    smoke_test = custom_tests / "test_smoke_cli.py"
    smoke_test.write_text(
        "import pytest\n\n"
        "@pytest.mark.smoke\n"
        "def test_smoke_cli_marker():\n"
        "    assert 1 == 1\n",
        encoding="utf-8",
    )

    run_res = _run_cli(
        "run",
        "--project-root",
        str(project_dir),
        "--data-dir",
        "custom_cases",
        "--test-dir",
        "generated_tests",
        "-k",
        "smoke_cli_marker",
    )
    assert run_res.returncode == 0, run_res.stdout + run_res.stderr
    combined = run_res.stdout + run_res.stderr
    assert "1 passed" in combined


def test_validate_json_output_for_valid_project(tmp_path):
    project_dir = tmp_path / "validate_project"
    init_res = _run_cli("init", str(project_dir))
    assert init_res.returncode == 0, init_res.stderr

    validate_res = _run_cli("validate", "--project-root", str(project_dir), "--json")
    assert validate_res.returncode == 0, validate_res.stdout + validate_res.stderr

    payload = json.loads(_last_nonempty_line(validate_res.stdout))
    assert payload["command"] == "validate"
    assert payload["summary"]["ok"] is True
    assert payload["summary"]["error_count"] == 0


def test_run_json_output_contains_summary(tmp_path):
    project_dir = tmp_path / "json_run_project"
    init_res = _run_cli("init", str(project_dir))
    assert init_res.returncode == 0, init_res.stderr

    gen_res = _run_cli("gen", "--project-root", str(project_dir))
    assert gen_res.returncode == 0, gen_res.stderr

    smoke_test = project_dir / "test_case" / "test_smoke_json.py"
    smoke_test.write_text(
        "import pytest\n\n"
        "@pytest.fixture\n"
        "def in_data():\n"
        "    return {\n"
        "        'url': 'https://example.com',\n"
        "        'method': 'GET',\n"
        "        'detail': 'smoke-json',\n"
        "        'assert_data': {'status_code': 200},\n"
        "        'headers': {},\n"
        "        'requestType': 'NONE',\n"
        "        'is_run': True,\n"
        "        'data': None,\n"
        "        'dependence_case': False,\n"
        "    }\n\n"
        "@pytest.mark.smoke\n"
        "def test_smoke_json_marker(in_data):\n"
        "    assert True\n",
        encoding="utf-8",
    )

    run_res = _run_cli(
        "run",
        "--project-root",
        str(project_dir),
        "--json",
        "-k",
        "smoke_json_marker",
    )
    assert run_res.returncode == 0, run_res.stdout + run_res.stderr

    payload = json.loads(_last_nonempty_line(run_res.stdout))
    assert payload["command"] == "run"
    assert payload["ok"] is True
    assert payload["pytest"]["summary"]["passed"] >= 1


def test_gen_force_overwrites_when_real_time_update_disabled(tmp_path):
    project_dir = tmp_path / "force_gen_project"
    init_res = _run_cli("init", str(project_dir))
    assert init_res.returncode == 0, init_res.stderr

    config_path = project_dir / "common" / "config.yaml"
    config_text = config_path.read_text(encoding="utf-8")
    config_text = config_text.replace(
        "real_time_update_test_cases: true",
        "real_time_update_test_cases: false",
    )
    config_path.write_text(config_text, encoding="utf-8")

    gen_res = _run_cli("gen", "--project-root", str(project_dir))
    assert gen_res.returncode == 0, gen_res.stderr

    generated_file = project_dir / "test_case" / "test_demo_banner.py"
    generated_file.write_text("# sentinel\n", encoding="utf-8")

    gen_no_force = _run_cli("gen", "--project-root", str(project_dir))
    assert gen_no_force.returncode == 0, gen_no_force.stderr
    assert generated_file.read_text(encoding="utf-8") == "# sentinel\n"

    gen_force = _run_cli("gen", "--project-root", str(project_dir), "--force")
    assert gen_force.returncode == 0, gen_force.stderr

    content = generated_file.read_text(encoding="utf-8")
    assert "# sentinel" not in content
    assert "from pytest_auto_api2.runtime.api import" in content
