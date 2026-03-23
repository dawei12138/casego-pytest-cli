#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Command-line entrypoint for pytest-auto-api2."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from common.setting import (
    CONFIG_PATH_ENV,
    DATA_DIR_ENV,
    PROJECT_ROOT_ENV,
    TEST_DIR_ENV,
)

DEFAULT_ALLURE_RESULTS_DIR = "report/tmp"
DEFAULT_ALLURE_HTML_DIR = "report/html"


class _PytestResultCollector:
    """Collect pytest summary for machine-readable JSON output."""

    def __init__(self) -> None:
        self.summary: Dict[str, Any] = {}
        self.failed_cases: List[Dict[str, Any]] = []
        self.error_cases: List[Dict[str, Any]] = []

    @staticmethod
    def _count_reports(stats: Dict[str, list], name: str) -> int:
        reports = stats.get(name, [])
        count = 0
        for report in reports:
            if getattr(report, "when", "call") != "teardown":
                count += 1
        return count

    @staticmethod
    def _collect_case_details(stats: Dict[str, list], key: str) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        for report in stats.get(key, []):
            if getattr(report, "when", "call") == "teardown":
                continue
            longrepr = getattr(report, "longreprtext", "")
            if longrepr and len(longrepr) > 1200:
                longrepr = longrepr[:1200] + "..."
            results.append(
                {
                    "nodeid": getattr(report, "nodeid", ""),
                    "when": getattr(report, "when", ""),
                    "longrepr": longrepr,
                }
            )
        return results

    def pytest_terminal_summary(self, terminalreporter):  # pragma: no cover - pytest hook
        stats = terminalreporter.stats

        collected = int(getattr(terminalreporter, "_numcollected", 0))
        passed = self._count_reports(stats, "passed")
        failed = self._count_reports(stats, "failed")
        errors = self._count_reports(stats, "error")
        skipped = self._count_reports(stats, "skipped")
        xfailed = self._count_reports(stats, "xfailed")
        xpassed = self._count_reports(stats, "xpassed")
        deselected = len(stats.get("deselected", []))

        start_time = getattr(terminalreporter, "_sessionstarttime", None)
        if start_time is None:
            session_start = getattr(terminalreporter, "_session_start", None)
            if hasattr(session_start, "timestamp"):
                start_time = session_start.timestamp()
            elif isinstance(session_start, (int, float)):
                start_time = float(session_start)

        duration = None
        if isinstance(start_time, (int, float)):
            duration = round(max(0.0, datetime.now().timestamp() - float(start_time)), 4)

        self.failed_cases = self._collect_case_details(stats, "failed")
        self.error_cases = self._collect_case_details(stats, "error")
        self.summary = {
            "collected": collected,
            "passed": passed,
            "failed": failed,
            "errors": errors,
            "skipped": skipped,
            "xfailed": xfailed,
            "xpassed": xpassed,
            "deselected": deselected,
            "duration_seconds": duration,
        }


def _resolve_project_root(project_root: Optional[str]) -> Path:
    if project_root:
        return Path(project_root).expanduser().resolve()
    env_root = os.getenv(PROJECT_ROOT_ENV)
    if env_root:
        return Path(env_root).expanduser().resolve()
    return Path.cwd().resolve()


def _resolve_path_from_root(root: Path, value: Optional[str], default_rel: str) -> Path:
    raw = value if value is not None else default_rel
    candidate = Path(raw)
    if candidate.is_absolute():
        return candidate.expanduser().resolve()
    return (root / candidate).expanduser().resolve()


def _apply_runtime_env(*, root: Path, config_path: Path, data_dir: Path, test_dir: Path) -> None:
    os.environ[PROJECT_ROOT_ENV] = str(root)
    os.environ[CONFIG_PATH_ENV] = str(config_path)
    os.environ[DATA_DIR_ENV] = str(data_dir)
    os.environ[TEST_DIR_ENV] = str(test_dir)


def _prepare_project(
    *,
    project_root: Optional[str],
    config: Optional[str],
    data_dir: Optional[str],
    test_dir: Optional[str],
    require_config: bool = True,
    require_data: bool = False,
    require_test: bool = False,
) -> Dict[str, Path]:
    root = _resolve_project_root(project_root)
    if not root.exists():
        raise FileNotFoundError(f"Project root does not exist: {root}")

    config_path = _resolve_path_from_root(root, config, "common/config.yaml")
    active_data_dir = _resolve_path_from_root(root, data_dir, "data")
    active_test_dir = _resolve_path_from_root(root, test_dir, "test_case")

    missing = []
    if require_config and not config_path.exists():
        missing.append(str(config_path))
    if require_data and not active_data_dir.exists():
        missing.append(str(active_data_dir))
    if require_test and not active_test_dir.exists():
        missing.append(str(active_test_dir))

    if missing:
        raise FileNotFoundError("Missing required project files/directories:\n" + "\n".join(missing))

    _apply_runtime_env(
        root=root,
        config_path=config_path,
        data_dir=active_data_dir,
        test_dir=active_test_dir,
    )

    return {
        "root": root,
        "config": config_path,
        "data": active_data_dir,
        "test": active_test_dir,
    }


def _get_allure_paths(project: Dict[str, Path], args: argparse.Namespace) -> Dict[str, Path]:
    result_dir = _resolve_path_from_root(project["root"], args.allure_dir, DEFAULT_ALLURE_RESULTS_DIR)
    html_dir = _resolve_path_from_root(project["root"], args.allure_html_dir, DEFAULT_ALLURE_HTML_DIR)
    return {"result": result_dir, "html": html_dir}


def _build_pytest_args(args: argparse.Namespace, project: Dict[str, Path]) -> List[str]:
    pytest_args: List[str] = ["-W", "ignore:Module already imported:pytest.PytestWarning"]

    # For machine-readable mode, keep output compact and stable.
    if getattr(args, "json", False):
        pytest_args.insert(0, "-q")
        if args.no_capture:
            pytest_args.insert(0, "-s")
    else:
        if not args.no_capture:
            pytest_args.insert(0, "-s")

    if args.marker:
        pytest_args.extend(["-m", args.marker])
    if args.keyword:
        pytest_args.extend(["-k", args.keyword])
    if args.maxfail is not None:
        pytest_args.extend(["--maxfail", str(args.maxfail)])

    if args.allure:
        allure_paths = _get_allure_paths(project, args)
        pytest_args.extend(["--alluredir", str(allure_paths["result"])])
        if args.clean_allure:
            pytest_args.append("--clean-alluredir")

    if args.targets:
        pytest_args.extend(args.targets)
    else:
        pytest_args.append(str(project["test"]))

    return pytest_args


def _allure_generate(project: Dict[str, Path], args: argparse.Namespace) -> None:
    allure_paths = _get_allure_paths(project, args)
    subprocess.run(
        [
            "allure",
            "generate",
            str(allure_paths["result"]),
            "-o",
            str(allure_paths["html"]),
            "--clean",
        ],
        check=True,
    )


def _allure_serve(project: Dict[str, Path], args: argparse.Namespace) -> None:
    allure_paths = _get_allure_paths(project, args)
    subprocess.run(
        [
            "allure",
            "serve",
            str(allure_paths["result"]),
            "-h",
            args.report_host,
            "-p",
            str(args.report_port),
        ],
        check=True,
    )


def _send_notifications() -> None:
    from utils import config
    from utils.notify.ding_talk import DingTalkSendMsg
    from utils.notify.lark import FeiShuTalkChatBot
    from utils.notify.send_mail import SendEmail
    from utils.notify.wechat_send import WeChatSend
    from utils.other_tools.allure_data.allure_report_data import AllureFileClean
    from utils.other_tools.models import NotificationType

    allure_data = AllureFileClean().get_case_count()
    notification_mapping = {
        NotificationType.DING_TALK.value: DingTalkSendMsg(allure_data).send_ding_notification,
        NotificationType.WECHAT.value: WeChatSend(allure_data).send_wechat_notification,
        NotificationType.EMAIL.value: SendEmail(allure_data).send_main,
        NotificationType.FEI_SHU.value: FeiShuTalkChatBot(allure_data).post,
    }

    notification_type = str(config.notification_type)
    if notification_type == NotificationType.DEFAULT.value:
        print("Notification skipped: notification_type is 0 in config.")
        return

    for item in notification_type.split(","):
        callback = notification_mapping.get(item.strip())
        if callback:
            callback()


def _write_excel_report() -> None:
    from utils.other_tools.allure_data.error_case_excel import ErrorCaseExcel

    ErrorCaseExcel().write_case()


def _print_json_output(payload: Dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def _build_run_json_payload(
    *,
    exit_code: int,
    project: Dict[str, Path],
    pytest_args: List[str],
    collector: Optional[_PytestResultCollector],
    report_generated: bool,
    report_served: bool,
    notified: bool,
    excel_report: bool,
) -> Dict[str, Any]:
    summary = collector.summary if collector is not None else {}
    failed_cases = collector.failed_cases if collector is not None else []
    error_cases = collector.error_cases if collector is not None else []

    return {
        "command": "run",
        "ok": exit_code == 0,
        "exit_code": exit_code,
        "timestamp": datetime.now().isoformat(),
        "project": {
            "root": str(project["root"]),
            "config": str(project["config"]),
            "data_dir": str(project["data"]),
            "test_dir": str(project["test"]),
        },
        "pytest": {
            "args": pytest_args,
            "summary": summary,
            "failed_cases": failed_cases,
            "error_cases": error_cases,
        },
        "post_actions": {
            "report_generated": report_generated,
            "report_served": report_served,
            "notified": notified,
            "excel_report": excel_report,
        },
    }


def _run_pytest(args: argparse.Namespace) -> int:
    if args.clean_allure and not args.allure:
        raise ValueError("--clean-allure requires --allure")

    report_flow_enabled = args.generate_report or args.serve_report or args.notify or args.excel_report
    if report_flow_enabled and not args.allure:
        raise ValueError("Report/notify options require --allure to be enabled.")

    project = _prepare_project(
        project_root=args.project_root,
        config=args.config,
        data_dir=args.data_dir,
        test_dir=args.test_dir,
        require_config=True,
        require_data=False,
        require_test=not bool(args.targets),
    )

    import pytest

    collector = _PytestResultCollector() if args.json else None
    plugins = [collector] if collector is not None else None

    report_generated = False
    report_served = False
    notified = False
    excel_report_generated = False

    old_cwd = Path.cwd()
    pytest_args = _build_pytest_args(args, project)
    try:
        os.chdir(project["root"])
        exit_code = int(pytest.main(pytest_args, plugins=plugins))

        if report_flow_enabled:
            _allure_generate(project, args)
            report_generated = True
        if args.notify:
            _send_notifications()
            notified = True
        if args.excel_report:
            _write_excel_report()
            excel_report_generated = True
        if args.serve_report:
            _allure_serve(project, args)
            report_served = True
    finally:
        os.chdir(old_cwd)

    if args.json:
        _print_json_output(
            _build_run_json_payload(
                exit_code=exit_code,
                project=project,
                pytest_args=pytest_args,
                collector=collector,
                report_generated=report_generated,
                report_served=report_served,
                notified=notified,
                excel_report=excel_report_generated,
            )
        )

    return exit_code


def _iter_yaml_files(data_dir: Path) -> List[Path]:
    files: List[Path] = []
    for pattern in ("*.yaml", "*.yml"):
        files.extend(sorted(p for p in data_dir.rglob(pattern) if p.is_file()))
    return files


def _validate_cases(args: argparse.Namespace) -> Dict[str, Any]:
    project = _prepare_project(
        project_root=args.project_root,
        config=args.config,
        data_dir=args.data_dir,
        test_dir=args.test_dir,
        require_config=True,
        require_data=True,
        require_test=False,
    )

    from utils.read_files_tools.get_yaml_data_analysis import CaseData
    from utils.read_files_tools.yaml_control import GetYamlData

    yaml_files = [p for p in _iter_yaml_files(project["data"]) if p.name != "proxy_data.yaml"]
    seen_case_ids: Dict[str, str] = {}
    errors: List[Dict[str, Any]] = []
    total_cases = 0

    for file_path in yaml_files:
        try:
            raw_data = GetYamlData(str(file_path)).get_yaml_data()
            if not isinstance(raw_data, dict):
                raise TypeError("yaml root must be a mapping/object")

            processed = CaseData(str(file_path)).case_process(case_id_switch=True) or []
            for item in processed:
                for case_id in item.keys():
                    total_cases += 1
                    if case_id in seen_case_ids:
                        errors.append(
                            {
                                "file": str(file_path),
                                "type": "duplicate_case_id",
                                "case_id": case_id,
                                "message": f"duplicate case_id already defined in {seen_case_ids[case_id]}",
                            }
                        )
                    else:
                        seen_case_ids[case_id] = str(file_path)

            if "case_common" not in raw_data:
                errors.append(
                    {
                        "file": str(file_path),
                        "type": "missing_case_common",
                        "case_id": None,
                        "message": "missing required top-level key: case_common",
                    }
                )

        except Exception as exc:
            errors.append(
                {
                    "file": str(file_path),
                    "type": "parse_or_schema_error",
                    "case_id": None,
                    "message": str(exc),
                }
            )
            if args.fail_fast:
                break

    payload = {
        "command": "validate",
        "timestamp": datetime.now().isoformat(),
        "project": {
            "root": str(project["root"]),
            "config": str(project["config"]),
            "data_dir": str(project["data"]),
            "test_dir": str(project["test"]),
        },
        "summary": {
            "total_yaml_files": len(yaml_files),
            "total_cases": total_cases,
            "error_count": len(errors),
            "ok": len(errors) == 0,
        },
        "errors": errors,
    }
    return payload


def _cmd_validate(args: argparse.Namespace) -> int:
    payload = _validate_cases(args)

    if args.json:
        _print_json_output(payload)
    else:
        summary = payload["summary"]
        print("Validation Summary")
        print(f"  project: {payload['project']['root']}")
        print(f"  yaml files: {summary['total_yaml_files']}")
        print(f"  cases: {summary['total_cases']}")
        print(f"  errors: {summary['error_count']}")
        if payload["errors"]:
            print("Validation Errors")
            for idx, item in enumerate(payload["errors"], start=1):
                case_id = item.get("case_id")
                extra = f", case_id={case_id}" if case_id else ""
                print(
                    f"  {idx}. file={item['file']}{extra}, type={item['type']}, message={item['message']}"
                )

    return 0 if payload["summary"]["ok"] else 2


def _cmd_gen(args: argparse.Namespace) -> int:
    project = _prepare_project(
        project_root=args.project_root,
        config=args.config,
        data_dir=args.data_dir,
        test_dir=args.test_dir,
        require_config=True,
        require_data=True,
        require_test=False,
    )

    old_cwd = Path.cwd()
    try:
        os.chdir(project["root"])
        from utils.read_files_tools.case_automatic_control import TestCaseAutomaticGeneration

        force_write = bool(getattr(args, "force", False) or getattr(args, "force_gen", False))
        TestCaseAutomaticGeneration(
            data_dir=str(project["data"]),
            test_dir=str(project["test"]),
            force_write=force_write,
        ).get_case_automatic()
    finally:
        os.chdir(old_cwd)

    print(f"Generated pytest cases from YAML under: {project['data']}")
    print(f"Generated files output directory: {project['test']}")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    return _run_pytest(args)


def _cmd_all(args: argparse.Namespace) -> int:
    _cmd_gen(args)
    return _run_pytest(args)


def _safe_write(path: Path, content: str, *, force: bool) -> bool:
    if path.exists() and not force:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def _template_config_yaml() -> str:
    return """project_name: demo-project

env: test
tester_name: qa
host: https://www.wanandroid.com
app_host:
real_time_update_test_cases: true
notification_type: \"0\"
excel_report: false

ding_talk:
  webhook:
  secret:

mysql_db:
  switch: false
  host:
  user: root
  password:
  port: 3306

mirror_source: https://pypi.org/simple/

wechat:
  webhook:

email:
  send_user:
  email_host: smtp.qq.com
  stamp_key:
  send_list:

lark:
  webhook:
"""


def _template_pytest_ini() -> str:
    return """[pytest]
addopts = -p no:warnings
testpaths = test_case/
python_files = test_*.py
python_classes = Test*
python_function = test_*

markers =
    smoke: smoke tests
"""


def _template_test_case_init() -> str:
    return """#!/usr/bin/env python
# -*- coding: utf-8 -*-

from pytest_auto_api2.runtime.loader import build_case_cache

build_case_cache()
"""


def _template_conftest() -> str:
    return """#!/usr/bin/env python
# -*- coding: utf-8 -*-

import ast
import allure
import pytest

from utils.other_tools.models import TestCase
from utils.other_tools.allure_data.allure_tools import allure_step, allure_step_no
from utils.read_files_tools.regular_control import cache_regular


def pytest_configure(config):
    config.addinivalue_line(\"markers\", \"smoke\")


@pytest.fixture(scope=\"function\", autouse=True)
def case_skip(in_data):
    in_data = TestCase(**in_data)
    if ast.literal_eval(cache_regular(str(in_data.is_run))) is False:
        allure.dynamic.title(in_data.detail)
        allure_step_no(f\"Request URL: {in_data.url}\")
        allure_step_no(f\"Request method: {in_data.method}\")
        allure_step(\"Headers\", in_data.headers)
        allure_step(\"Request body\", in_data.data)
        allure_step(\"Dependence data\", in_data.dependence_case_data)
        allure_step(\"Assert data\", in_data.assert_data)
        pytest.skip()
"""


def _template_sample_yaml() -> str:
    return """case_common:
  allureEpic: Demo API
  allureFeature: Banner module
  allureStory: Banner list API

demo_banner_list_01:
  host: ${{host()}}
  url: /banner/json
  method: GET
  detail: banner list should return success
  headers:
    Content-Type: application/json
  requestType: None
  is_run: true
  data:
  dependence_case: false
  dependence_case_data:
  assert:
    errorCode:
      jsonpath: $.errorCode
      type: ==
      value: 0
      AssertType:
    status_code: 200
"""


def _template_run_py() -> str:
    return """#!/usr/bin/env python
# -*- coding: utf-8 -*-

from pytest_auto_api2.cli import main as casego_main


if __name__ == "__main__":
    raise SystemExit(
        casego_main(
            [
                "all",
                "--project-root",
                ".",
                "--allure",
                "--generate-report",
            ]
        )
    )
"""


def _cmd_init(args: argparse.Namespace) -> int:
    target = Path.cwd().resolve()
    target.mkdir(parents=True, exist_ok=True)

    for name in ("common", "data", "test_case", "Files", "logs", "report"):
        (target / name).mkdir(parents=True, exist_ok=True)

    template_files = {
        target / "common" / "config.yaml": _template_config_yaml(),
        target / "pytest.ini": _template_pytest_ini(),
        target / "run.py": _template_run_py(),
        target / "test_case" / "__init__.py": _template_test_case_init(),
        target / "test_case" / "conftest.py": _template_conftest(),
        target / "data" / "demo_banner.yaml": _template_sample_yaml(),
    }

    created = []
    skipped = []
    for path, content in template_files.items():
        if _safe_write(path, content, force=args.force):
            created.append(path)
        else:
            skipped.append(path)

    print(f"Initialized project scaffold at: {target}")
    if created:
        print("Created/updated files:")
        for item in created:
            print(f"  - {item}")
    if skipped:
        print("Skipped existing files (use --force to overwrite):")
        for item in skipped:
            print(f"  - {item}")

    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="casego",
        description="Generate pytest cases from YAML and run API tests.",
    )

    project_common = argparse.ArgumentParser(add_help=False)
    project_common.add_argument(
        "--project-root",
        default=None,
        help=f"Project root path. Defaults to current directory or {PROJECT_ROOT_ENV}.",
    )
    project_common.add_argument(
        "--config",
        default=None,
        help=f"Config file path. Defaults to common/config.yaml or {CONFIG_PATH_ENV}.",
    )
    project_common.add_argument(
        "--data-dir",
        default=None,
        help=f"YAML data directory. Defaults to data or {DATA_DIR_ENV}.",
    )
    project_common.add_argument(
        "--test-dir",
        default=None,
        help=f"Generated test directory. Defaults to test_case or {TEST_DIR_ENV}.",
    )

    run_common = argparse.ArgumentParser(add_help=False)
    for action in project_common._actions:
        if action.dest != "help":
            run_common._add_action(action)

    run_common.add_argument("-k", "--keyword", default=None, help="Pytest -k expression.")
    run_common.add_argument("-m", "--marker", default=None, help="Pytest marker expression.")
    run_common.add_argument(
        "--maxfail", type=int, default=None, help="Stop after N test failures."
    )
    run_common.add_argument(
        "--no-capture",
        action="store_true",
        help="Disable default -s behavior. If set, output capture is enabled.",
    )
    run_common.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON result summary.",
    )
    run_common.add_argument(
        "--allure",
        action="store_true",
        help="Enable Allure results collection (--alluredir).",
    )
    run_common.add_argument(
        "--clean-allure",
        action="store_true",
        help="Clean allure results directory before run (requires --allure).",
    )
    run_common.add_argument(
        "--allure-dir",
        default=DEFAULT_ALLURE_RESULTS_DIR,
        help=f"Allure results directory. Default: {DEFAULT_ALLURE_RESULTS_DIR}",
    )
    run_common.add_argument(
        "--allure-html-dir",
        default=DEFAULT_ALLURE_HTML_DIR,
        help=f"Allure HTML output directory. Default: {DEFAULT_ALLURE_HTML_DIR}",
    )
    run_common.add_argument(
        "--generate-report",
        action="store_true",
        help="Generate allure HTML report after pytest run (requires --allure).",
    )
    run_common.add_argument(
        "--serve-report",
        action="store_true",
        help="Serve allure report after run (requires --allure).",
    )
    run_common.add_argument(
        "--report-host",
        default="127.0.0.1",
        help="Host used by `allure serve`. Default: 127.0.0.1",
    )
    run_common.add_argument(
        "--report-port",
        type=int,
        default=9999,
        help="Port used by `allure serve`. Default: 9999",
    )
    run_common.add_argument(
        "--notify",
        action="store_true",
        help="Send notifications based on notification_type in config (requires --allure).",
    )
    run_common.add_argument(
        "--excel-report",
        action="store_true",
        help="Generate failed-case excel report (requires --allure).",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    gen_parser = subparsers.add_parser(
        "gen",
        parents=[project_common],
        help="Generate pytest test files from YAML data.",
    )
    gen_parser.add_argument(
        "--force",
        action="store_true",
        help="Force overwrite generated testcase files regardless of real_time_update_test_cases.",
    )
    gen_parser.set_defaults(func=_cmd_gen)

    validate_parser = subparsers.add_parser(
        "validate",
        parents=[project_common],
        help="Validate YAML test definitions before generation or execution.",
    )
    validate_parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON validation result.",
    )
    validate_parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop validation on first parse/schema error.",
    )
    validate_parser.set_defaults(func=_cmd_validate)

    run_parser = subparsers.add_parser(
        "run",
        parents=[run_common],
        help="Run pytest for generated cases.",
    )
    run_parser.add_argument(
        "targets",
        nargs="*",
        help="Optional pytest targets (file/dir/nodeid). Default: configured test directory",
    )
    run_parser.set_defaults(func=_cmd_run)

    all_parser = subparsers.add_parser(
        "all",
        parents=[run_common],
        help="Generate cases and then run pytest.",
    )
    all_parser.add_argument(
        "--force-gen",
        action="store_true",
        help="Force overwrite generated testcase files during the gen step.",
    )
    all_parser.add_argument(
        "targets",
        nargs="*",
        help="Optional pytest targets (file/dir/nodeid). Default: configured test directory",
    )
    all_parser.set_defaults(func=_cmd_all)

    init_parser = subparsers.add_parser(
        "ini",
        aliases=["init"],
        help="Initialize project scaffold in current directory.",
    )
    init_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite scaffold files if they already exist.",
    )
    init_parser.set_defaults(func=_cmd_init)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except Exception as exc:
        print(f"casego command failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

