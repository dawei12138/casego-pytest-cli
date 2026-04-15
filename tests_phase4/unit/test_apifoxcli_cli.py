from contextlib import contextmanager
import json
from pathlib import Path
import time
from types import SimpleNamespace

import pytest_auto_api2.apifoxcli.cli as cli_module
from pytest_auto_api2.apifoxcli.cli import build_parser, main


def test_build_parser_supports_project_init():
    parser = build_parser()
    args = parser.parse_args(["project", "init", "--project-root", "demo", "--name", "demo-api"])
    assert args.resource == "project"
    assert args.action == "init"
    assert args.project_root == "demo"
    assert args.name == "demo-api"
    assert args.default_env == "qa"


def test_build_parser_supports_api_send():
    parser = build_parser()
    args = parser.parse_args(["api", "send", "user.login", "--env", "qa", "--json"])
    assert args.resource == "api"
    assert args.action == "send"
    assert args.resource_id == "user.login"
    assert args.env == "qa"
    assert args.json is True


def test_build_parser_supports_flow_run():
    parser = build_parser()
    args = parser.parse_args(
        ["flow", "run", "auth.bootstrap", "--env", "qa", "--dataset", "auth.users", "--json"]
    )
    assert args.resource == "flow"
    assert args.action == "run"
    assert args.resource_id == "auth.bootstrap"
    assert args.env == "qa"
    assert args.dataset == "auth.users"
    assert args.json is True


def test_build_parser_supports_project_import_openapi():
    parser = build_parser()
    args = parser.parse_args(
        [
            "project",
            "import-openapi",
            "--project-root",
            "demo",
            "--source",
            "https://example.com/openapi.json",
            "--server-description",
            "qa",
            "--include-path",
            "/login",
            "--include-path",
            "/getInfo",
        ]
    )
    assert args.resource == "project"
    assert args.action == "import-openapi"
    assert args.project_root == "demo"
    assert args.source == "https://example.com/openapi.json"
    assert args.server_description == "qa"
    assert args.include_path == ["/login", "/getInfo"]


def test_main_unknown_command_returns_non_zero():
    exit_code = main(["validate", "--project-root", "missing-project"])
    assert exit_code != 0


def test_validate_returns_exit_code_2_for_unsupported_expression(tmp_path):
    apifox = tmp_path / "apifox"
    (apifox / "envs").mkdir(parents=True)
    (apifox / "apis").mkdir()
    (apifox / "project.yaml").write_text(
        "kind: project\nid: default\nname: demo\nspec:\n  defaultEnv: qa\n",
        encoding="utf-8",
    )
    (apifox / "envs" / "qa.yaml").write_text(
        "kind: env\nid: qa\nname: qa\nspec:\n  baseUrl: http://example.com\n  variables: {}\n",
        encoding="utf-8",
    )
    (apifox / "apis" / "broken.yaml").write_text(
        "kind: api\nid: broken.api\nname: broken\nspec:\n  protocol: http\n  envRef: qa\n  request:\n    method: GET\n    path: /broken\n    headers:\n      Authorization: ${bad.token}\n  expect:\n    status: 200\n    assertions: []\n",
        encoding="utf-8",
    )

    exit_code = main(["validate", "--project-root", str(tmp_path)])
    assert exit_code == 2


def test_api_send_without_json_prints_text_summary(monkeypatch, capsys):
    monkeypatch.setattr(cli_module, "emit_execution_log", lambda _detail: None)
    report_dir = Path("D:/reports/demo-run")
    logs_dir = Path("D:/logs/info-2026-04-14.log")
    monkeypatch.setattr(
        cli_module,
        "_bind_run_logs",
        lambda _project, _summary: {"primary": logs_dir, "paths": {"info": logs_dir}},
    )
    monkeypatch.setattr(
        cli_module,
        "write_run_report",
        lambda **_kwargs: SimpleNamespace(
            path=report_dir,
            logs_path=logs_dir,
            log_paths={"info": logs_dir},
            to_payload=lambda: {
                "path": str(report_dir),
                "logs": str(logs_dir),
                "logPaths": {"info": str(logs_dir)},
            },
        ),
    )
    monkeypatch.setattr(
        cli_module,
        "load_project",
        lambda _root: SimpleNamespace(
            root=Path("D:/project/demo"),
            apis={"auth.post.login": object()},
            cases={},
            flows={},
            suites={},
            sources={},
            envs={},
            datasets={},
        ),
    )
    monkeypatch.setattr(
        cli_module,
        "run_api",
        lambda _project, _resource_id, _env, _dataset: SimpleNamespace(
            total=1,
            passed=1,
            failed=0,
            details=[
                {
                    "resource_id": "auth.post.login",
                    "env_id": "demo",
                    "status_code": 200,
                    "request": {
                        "method": "POST",
                        "url": "https://demo.example.dev/login",
                    },
                }
            ],
        ),
    )

    exit_code = main(["api", "send", "auth.post.login", "--project-root", "demo"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "PASS api auth.post.login total=1 passed=1 failed=0" in captured.out
    assert "- auth.post.login env=demo POST https://demo.example.dev/login status=200" in captured.out
    assert f"report: {report_dir}" in captured.out
    assert f"logs:   {logs_dir}" in captured.out
    assert captured.err == ""


def test_flow_run_without_json_prints_text_summary(monkeypatch, capsys):
    monkeypatch.setattr(cli_module, "emit_execution_log", lambda _detail: None)
    report_dir = Path("D:/reports/flow-run")
    logs_dir = Path("D:/logs/info-2026-04-14.log")
    monkeypatch.setattr(
        cli_module,
        "_bind_run_logs",
        lambda _project, _summary: {"primary": logs_dir, "paths": {"info": logs_dir}},
    )
    monkeypatch.setattr(
        cli_module,
        "write_run_report",
        lambda **_kwargs: SimpleNamespace(
            path=report_dir,
            logs_path=logs_dir,
            log_paths={"info": logs_dir},
            to_payload=lambda: {
                "path": str(report_dir),
                "logs": str(logs_dir),
                "logPaths": {"info": str(logs_dir)},
            },
        ),
    )
    monkeypatch.setattr(
        cli_module,
        "load_project",
        lambda _root: SimpleNamespace(
            root=Path("D:/project/demo"),
            apis={},
            cases={},
            flows={"auth.chain.guest": object()},
            suites={},
            sources={},
            envs={},
            datasets={},
        ),
    )
    monkeypatch.setattr(
        cli_module,
        "run_flow",
        lambda _project, _resource_id, _env, _dataset: SimpleNamespace(
            total=2,
            passed=2,
            failed=0,
            details=[
                {
                    "resource_id": "auth.login.guest",
                    "env_id": "demo",
                    "status_code": 200,
                    "request": {
                        "method": "POST",
                        "url": "https://demo.example.dev/login",
                    },
                },
                {
                    "resource_id": "auth.get-info.smoke",
                    "env_id": "demo",
                    "status_code": 200,
                    "request": {
                        "method": "GET",
                        "url": "https://demo.example.dev/getInfo",
                    },
                },
            ],
        ),
    )

    exit_code = main(["flow", "run", "auth.chain.guest", "--project-root", "demo"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "PASS flow auth.chain.guest total=2 passed=2 failed=0" in captured.out
    assert "- auth.login.guest env=demo POST https://demo.example.dev/login status=200" in captured.out
    assert "- auth.get-info.smoke env=demo GET https://demo.example.dev/getInfo status=200" in captured.out
    assert f"report: {report_dir}" in captured.out
    assert f"logs:   {logs_dir}" in captured.out
    assert captured.err == ""


def test_api_send_emits_execution_logs(monkeypatch):
    emitted = []
    monkeypatch.setattr(cli_module, "emit_execution_log", lambda detail: emitted.append(detail))
    report_dir = Path("D:/reports/json-run")
    logs_dir = Path("D:/logs/info-2026-04-14.log")

    @contextmanager
    def _fake_temp_logs(_project_root):
        yield {"info": logs_dir, "error": Path("D:/logs/error-2026-04-14.log"), "warning": Path("D:/logs/warning.log")}

    monkeypatch.setattr(cli_module, "temporary_runtime_loggers", _fake_temp_logs)
    monkeypatch.setattr(
        cli_module,
        "write_run_report",
        lambda **_kwargs: SimpleNamespace(
            path=report_dir,
            logs_path=logs_dir,
            log_paths={"info": logs_dir},
            to_payload=lambda: {
                "path": str(report_dir),
                "logs": str(logs_dir),
                "logPaths": {"info": str(logs_dir)},
            },
        ),
    )
    monkeypatch.setattr(
        cli_module,
        "load_project",
        lambda _root: SimpleNamespace(
            root=Path("D:/project/demo"),
            apis={"auth.post.login": object()},
            cases={},
            flows={},
            suites={},
            sources={},
            envs={},
            datasets={},
        ),
    )
    monkeypatch.setattr(
        cli_module,
        "run_api",
        lambda _project, _resource_id, _env, _dataset: SimpleNamespace(
            total=1,
            passed=1,
            failed=0,
            details=[{"resource_id": "auth.post.login", "status_code": 200}],
        ),
    )

    exit_code = main(["api", "send", "auth.post.login", "--project-root", "demo", "--json"])

    assert exit_code == 0
    assert emitted == [{"resource_id": "auth.post.login", "status_code": 200}]


def test_api_send_with_json_includes_report_payload(monkeypatch, capsys):
    monkeypatch.setattr(cli_module, "emit_execution_log", lambda _detail: None)
    report_dir = Path("D:/reports/json-run")
    logs_dir = Path("D:/logs/info-2026-04-14.log")
    monkeypatch.setattr(
        cli_module,
        "_bind_run_logs",
        lambda _project, _summary: {"primary": logs_dir, "paths": {"info": logs_dir}},
    )
    monkeypatch.setattr(
        cli_module,
        "write_run_report",
        lambda **_kwargs: SimpleNamespace(
            path=report_dir,
            logs_path=logs_dir,
            log_paths={"info": logs_dir},
            to_payload=lambda: {
                "path": str(report_dir),
                "logs": str(logs_dir),
                "logPaths": {"info": str(logs_dir)},
            },
        ),
    )
    monkeypatch.setattr(
        cli_module,
        "load_project",
        lambda _root: SimpleNamespace(
            root=Path("D:/project/demo"),
            apis={"auth.post.login": object()},
            cases={},
            flows={},
            suites={},
            sources={},
            envs={},
            datasets={},
        ),
    )
    monkeypatch.setattr(
        cli_module,
        "run_api",
        lambda _project, _resource_id, _env, _dataset: SimpleNamespace(
            total=1,
            passed=1,
            failed=0,
            details=[{"resource_id": "auth.post.login", "status_code": 200}],
        ),
    )

    exit_code = main(["api", "send", "auth.post.login", "--project-root", "demo", "--json"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out.strip())

    assert exit_code == 0
    assert payload["total"] == 1
    assert payload["report"] == {
        "path": str(report_dir),
        "logs": str(logs_dir),
        "logPaths": {"info": str(logs_dir)},
    }
    assert captured.err == ""


def test_flow_run_with_mixed_results_surfaces_both_log_files(monkeypatch, capsys):
    report_dir = Path("D:/reports/mixed-flow")
    log_paths = {
        "info": Path("D:/logs/info-2026-04-14.log"),
        "error": Path("D:/logs/error-2026-04-14.log"),
    }
    monkeypatch.setattr(cli_module, "_emit_execution_logs", lambda _summary: None)
    monkeypatch.setattr(
        cli_module,
        "_bind_run_logs",
        lambda _project, _summary: {
            "primary": log_paths["error"],
            "paths": log_paths,
        },
    )
    monkeypatch.setattr(
        cli_module,
        "write_run_report",
        lambda **_kwargs: SimpleNamespace(
            path=report_dir,
            logs_path=log_paths["error"],
            log_paths=log_paths,
            to_payload=lambda: {
                "path": str(report_dir),
                "logs": str(log_paths["error"]),
                "logPaths": {key: str(value) for key, value in log_paths.items()},
            },
        ),
    )
    monkeypatch.setattr(
        cli_module,
        "load_project",
        lambda _root: SimpleNamespace(
            root=Path("D:/project/demo"),
            apis={},
            cases={},
            flows={"auth.chain.guest": object()},
            suites={},
            sources={},
            envs={},
            datasets={},
        ),
    )
    monkeypatch.setattr(
        cli_module,
        "run_flow",
        lambda _project, _resource_id, _env, _dataset: SimpleNamespace(
            total=2,
            passed=1,
            failed=1,
            details=[
                {
                    "resource_id": "auth.login.guest",
                    "env_id": "demo",
                    "status_code": 200,
                    "request": {"method": "POST", "url": "https://demo.example.dev/login"},
                },
                {
                    "resource_id": "auth.get-info.smoke",
                    "env_id": "demo",
                    "status_code": 500,
                    "error": "status mismatch",
                    "request": {"method": "GET", "url": "https://demo.example.dev/getInfo"},
                },
            ],
        ),
    )

    exit_code = main(["flow", "run", "auth.chain.guest", "--project-root", "demo", "--json"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out.strip())

    assert exit_code == 1
    assert payload["report"]["logs"] == str(log_paths["error"])
    assert payload["report"]["logPaths"] == {key: str(value) for key, value in log_paths.items()}


def test_flow_run_with_mixed_results_prints_extra_log_lines(monkeypatch, capsys):
    report_dir = Path("D:/reports/mixed-flow")
    log_paths = {
        "info": Path("D:/logs/info-2026-04-14.log"),
        "error": Path("D:/logs/error-2026-04-14.log"),
    }
    monkeypatch.setattr(cli_module, "_emit_execution_logs", lambda _summary: None)
    monkeypatch.setattr(
        cli_module,
        "_bind_run_logs",
        lambda _project, _summary: {
            "primary": log_paths["error"],
            "paths": log_paths,
        },
    )
    monkeypatch.setattr(
        cli_module,
        "write_run_report",
        lambda **_kwargs: SimpleNamespace(
            path=report_dir,
            logs_path=log_paths["error"],
            log_paths=log_paths,
            to_payload=lambda: {
                "path": str(report_dir),
                "logs": str(log_paths["error"]),
                "logPaths": {key: str(value) for key, value in log_paths.items()},
            },
        ),
    )
    monkeypatch.setattr(
        cli_module,
        "load_project",
        lambda _root: SimpleNamespace(
            root=Path("D:/project/demo"),
            apis={},
            cases={},
            flows={"auth.chain.guest": object()},
            suites={},
            sources={},
            envs={},
            datasets={},
        ),
    )
    monkeypatch.setattr(
        cli_module,
        "run_flow",
        lambda _project, _resource_id, _env, _dataset: SimpleNamespace(
            total=2,
            passed=1,
            failed=1,
            details=[
                {
                    "resource_id": "auth.login.guest",
                    "env_id": "demo",
                    "status_code": 200,
                    "request": {"method": "POST", "url": "https://demo.example.dev/login"},
                },
                {
                    "resource_id": "auth.get-info.smoke",
                    "env_id": "demo",
                    "status_code": 500,
                    "error": "status mismatch",
                    "request": {"method": "GET", "url": "https://demo.example.dev/getInfo"},
                },
            ],
        ),
    )

    exit_code = main(["flow", "run", "auth.chain.guest", "--project-root", "demo"])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "FAIL flow auth.chain.guest total=2 passed=1 failed=1" in captured.out
    assert "error=status mismatch" in captured.out
    assert f"logs:   {log_paths['error']}" in captured.out
    assert f"logs.info: {log_paths['info']}" in captured.out


def test_api_send_with_project_root_restores_logger_targets_after_run(monkeypatch, tmp_path):
    from pytest_auto_api2.utils.logging_tool import log_control as log_control_module

    original_paths = {
        "info": Path(log_control_module.INFO.log_path),
        "error": Path(log_control_module.ERROR.log_path),
        "warning": Path(log_control_module.WARNING.log_path),
    }
    project_root = tmp_path / "target-project"
    project_root.mkdir()
    other_cwd = tmp_path / "other-cwd"
    other_cwd.mkdir()
    monkeypatch.chdir(other_cwd)
    monkeypatch.setattr(
        cli_module,
        "load_project",
        lambda _root: SimpleNamespace(
            root=project_root,
            apis={"auth.post.login": object()},
            cases={},
            flows={},
            suites={},
            sources={},
            envs={},
            datasets={},
        ),
    )
    monkeypatch.setattr(
        cli_module,
        "run_api",
        lambda _project, _resource_id, _env, _dataset: SimpleNamespace(
            total=1,
            passed=1,
            failed=0,
            details=[{"resource_id": "auth.post.login", "status_code": 200}],
        ),
    )

    exit_code = main(["api", "send", "auth.post.login", "--project-root", str(project_root), "--json"])

    assert exit_code == 0
    assert Path(log_control_module.INFO.log_path) == original_paths["info"]
    assert Path(log_control_module.ERROR.log_path) == original_paths["error"]
    assert Path(log_control_module.WARNING.log_path) == original_paths["warning"]


def test_api_send_with_project_root_rebinds_reported_log_file(monkeypatch, tmp_path, capsys):
    from pytest_auto_api2.utils.logging_tool import log_control as log_control_module

    original_root = Path(log_control_module.INFO.log_path).resolve().parents[1]
    project_root = tmp_path / "target-project"
    project_root.mkdir()
    other_cwd = tmp_path / "other-cwd"
    other_cwd.mkdir()
    monkeypatch.chdir(other_cwd)
    monkeypatch.setattr(
        cli_module,
        "load_project",
        lambda _root: SimpleNamespace(
            root=project_root,
            apis={"auth.post.login": object()},
            cases={},
            flows={},
            suites={},
            sources={},
            envs={},
            datasets={},
        ),
    )
    monkeypatch.setattr(
        cli_module,
        "run_api",
        lambda _project, _resource_id, _env, _dataset: SimpleNamespace(
            total=1,
            passed=1,
            failed=0,
            details=[
                {
                    "resource_id": "auth.post.login",
                    "title": "login",
                    "env_id": "demo",
                    "status_code": 200,
                    "request": {
                        "method": "POST",
                        "url": "https://demo.example.dev/login",
                        "headers": {},
                    },
                    "response": {"status_code": 200, "body": {"ok": True}},
                }
            ],
        ),
    )

    try:
        exit_code = main(["api", "send", "auth.post.login", "--project-root", str(project_root), "--json"])
    finally:
        log_control_module.rebind_runtime_loggers(original_root)

    captured = capsys.readouterr()
    payload = json.loads(captured.out.strip())
    expected_log_path = (project_root / "logs" / f"info-{time.strftime('%Y-%m-%d', time.localtime())}.log").resolve()

    assert exit_code == 0
    assert payload["report"]["logs"] == str(expected_log_path)
    assert expected_log_path.is_file()
    assert str(project_root.resolve()) in payload["report"]["path"]


def test_suite_run_without_json_prints_text_summary_and_report_paths(monkeypatch, capsys):
    monkeypatch.setattr(cli_module, "emit_execution_log", lambda _detail: None)
    report_dir = Path("D:/reports/suite-run")
    logs_file = Path("D:/logs/info-2026-04-14.log")
    monkeypatch.setattr(
        cli_module,
        "_bind_run_logs",
        lambda _project, _summary: {"primary": logs_file, "paths": {"info": logs_file}},
    )
    monkeypatch.setattr(
        cli_module,
        "write_run_report",
        lambda **_kwargs: SimpleNamespace(
            path=report_dir,
            logs_path=logs_file,
            log_paths={"info": logs_file},
            to_payload=lambda: {
                "path": str(report_dir),
                "logs": str(logs_file),
                "logPaths": {"info": str(logs_file)},
            },
        ),
    )
    monkeypatch.setattr(
        cli_module,
        "load_project",
        lambda _root: SimpleNamespace(
            root=Path("D:/project/demo"),
            apis={},
            cases={},
            flows={},
            suites={"auth.smoke": object()},
            sources={},
            envs={},
            datasets={},
        ),
    )
    monkeypatch.setattr(
        cli_module,
        "run_suite",
        lambda _project, _resource_id, _env: SimpleNamespace(
            total=1,
            passed=1,
            failed=0,
            details=[
                {
                    "resource_id": "auth.login.guest",
                    "env_id": "demo",
                    "status_code": 200,
                    "request": {
                        "method": "POST",
                        "url": "https://demo.example.dev/login",
                    },
                }
            ],
        ),
    )

    exit_code = main(["suite", "run", "auth.smoke", "--project-root", "demo"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "PASS suite auth.smoke total=1 passed=1 failed=0" in captured.out
    assert "- auth.login.guest env=demo POST https://demo.example.dev/login status=200" in captured.out
    assert f"report: {report_dir}" in captured.out
    assert f"logs:   {logs_file}" in captured.out
    assert captured.err == ""


def test_api_send_with_case_id_prints_clear_type_aware_error(tmp_path, capsys):
    apifox = tmp_path / "apifox"
    (apifox / "cases").mkdir(parents=True)
    (apifox / "envs").mkdir()
    (apifox / "project.yaml").write_text(
        "kind: project\nid: default\nname: demo\nspec:\n  defaultEnv: qa\n",
        encoding="utf-8",
    )
    (apifox / "envs" / "qa.yaml").write_text(
        "kind: env\nid: qa\nname: qa\nspec:\n  baseUrl: http://example.com\n  variables: {}\n",
        encoding="utf-8",
    )
    (apifox / "cases" / "login.yaml").write_text(
        "kind: case\nid: auth.login.guest\nname: login guest\nspec:\n  apiRef: auth.post.login\n  request: {}\n  expect:\n    status: 200\n    assertions: []\n  extract: []\n",
        encoding="utf-8",
    )

    exit_code = main(["api", "send", "auth.login.guest", "--project-root", str(tmp_path)])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert captured.out == ""
    assert "resource 'auth.login.guest' is a case; use: apifoxcli case send auth.login.guest" in captured.err
