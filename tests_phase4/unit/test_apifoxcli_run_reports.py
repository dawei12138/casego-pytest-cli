import re

import yaml

from pytest_auto_api2.apifoxcli.run_reports import write_run_report


def test_write_run_report_creates_expected_artifacts(tmp_path):
    project_root = tmp_path / "demo"
    summary = {
        "total": 1,
        "passed": 1,
        "failed": 0,
        "details": [
            {
                "resource_id": "auth.login.guest",
                "env_id": "qa",
                "status_code": 200,
                "request": {
                    "method": "POST",
                    "url": "https://demo.example.dev/login",
                },
            }
        ],
    }
    console_lines = [
        "PASS case auth.login.guest total=1 passed=1 failed=0",
        "- auth.login.guest env=qa POST https://demo.example.dev/login status=200",
    ]

    report = write_run_report(
        project_root=project_root,
        kind="case",
        resource_id="auth.login.guest",
        summary=summary,
        console_lines=console_lines,
        logs_path=project_root / "logs" / "info-2026-04-14.log",
    )

    report_dir = report.path
    assert report_dir.is_dir()
    assert report.summary_path.is_file()
    assert report.tree_path.is_file()
    assert report.console_path.is_file()
    node_files = sorted(report.nodes_path.glob("*.yaml"))
    assert node_files
    assert report.logs_path == (project_root / "logs" / "info-2026-04-14.log").resolve()

    relative_parts = report_dir.relative_to(project_root.resolve()).parts
    assert relative_parts[:3] == ("apifox", "reports", "runs")
    assert relative_parts[3] == report.date
    assert relative_parts[4] == report.run_id
    assert len(relative_parts) == 5
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", report.date)
    assert re.fullmatch(r"\d{12}-[0-9a-f]{8}", report.run_id)

    summary_payload = yaml.safe_load(report.summary_path.read_text(encoding="utf-8"))
    assert summary_payload["resource"]["kind"] == "case"
    assert summary_payload["resource"]["id"] == "auth.login.guest"
    assert summary_payload["summary"] == {"total": 1, "passed": 1, "failed": 0}

    assert "auth.login.guest" in report.tree_path.read_text(encoding="utf-8")
    assert report.console_path.read_text(encoding="utf-8").splitlines() == console_lines


def test_write_run_report_keeps_non_lossy_log_metadata(tmp_path):
    project_root = tmp_path / "demo"
    report = write_run_report(
        project_root=project_root,
        kind="flow",
        resource_id="auth.chain.guest",
        summary={"total": 2, "passed": 1, "failed": 1, "details": []},
        console_lines=["FAIL flow auth.chain.guest total=2 passed=1 failed=1"],
        logs_path=project_root / "logs" / "error-2026-04-14.log",
        log_paths={
            "info": project_root / "logs" / "info-2026-04-14.log",
            "error": project_root / "logs" / "error-2026-04-14.log",
        },
    )

    payload = report.to_payload()
    assert payload["logs"] == str((project_root / "logs" / "error-2026-04-14.log").resolve())
    assert payload["logPaths"] == {
        "info": str((project_root / "logs" / "info-2026-04-14.log").resolve()),
        "error": str((project_root / "logs" / "error-2026-04-14.log").resolve()),
    }
