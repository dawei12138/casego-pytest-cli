from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence
from uuid import uuid4

import yaml


_SAFE_FILE_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(frozen=True)
class RunReport:
    path: Path
    summary_path: Path
    tree_path: Path
    console_path: Path
    nodes_path: Path
    logs_path: Path
    run_id: str
    date: str
    log_paths: Dict[str, Path] = field(default_factory=dict)

    def to_payload(self) -> Dict[str, Any]:
        return {
            "path": str(self.path),
            "logs": str(self.logs_path),
            "logPaths": {name: str(path) for name, path in self.log_paths.items()},
            "summary": str(self.summary_path),
            "tree": str(self.tree_path),
            "console": str(self.console_path),
            "nodes": str(self.nodes_path),
            "runId": self.run_id,
            "date": self.date,
        }


def _sanitize_filename(value: str) -> str:
    sanitized = _SAFE_FILE_CHARS.sub("-", value).strip("-")
    return sanitized or "node"


def _summary_counts(summary: Mapping[str, Any]) -> Dict[str, int]:
    return {
        "total": int(summary.get("total", 0) or 0),
        "passed": int(summary.get("passed", 0) or 0),
        "failed": int(summary.get("failed", 0) or 0),
    }


def _build_tree_lines(kind: str, resource_id: str, summary: Mapping[str, Any]) -> Sequence[str]:
    details = list(summary.get("details") or [])
    outcome = "PASS" if _summary_counts(summary)["failed"] == 0 else "FAIL"
    lines = [f"{outcome} {kind} {resource_id}"]
    for index, detail in enumerate(details):
        branch = "`- " if index == len(details) - 1 else "|- "
        node_status = "FAIL" if detail.get("error") else "PASS"
        detail_id = str(detail.get("resource_id") or resource_id)
        parts = [f"{branch}{node_status} {detail_id}"]
        env_id = detail.get("env_id")
        if env_id:
            parts.append(f"env={env_id}")
        status_code = detail.get("status_code")
        if status_code is not None:
            parts.append(f"status={status_code}")
        lines.append(" ".join(parts))
    return lines


def _write_yaml(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(yaml.safe_dump(dict(payload), allow_unicode=True, sort_keys=False), encoding="utf-8")


def write_console_log(report: RunReport, console_lines: Sequence[str]) -> Path:
    body = "\n".join(console_lines)
    if console_lines:
        body += "\n"
    report.console_path.write_text(body, encoding="utf-8")
    return report.console_path


def write_run_report(
    *,
    project_root: Path,
    kind: str,
    resource_id: str,
    summary: Mapping[str, Any],
    console_lines: Sequence[str],
    logs_path: Path,
    log_paths: Mapping[str, Path] | None = None,
) -> RunReport:
    canonical_root = Path(project_root).resolve()
    generated_at = datetime.now().astimezone()
    date_str = generated_at.strftime("%Y-%m-%d")
    run_id = f"{generated_at.strftime('%H%M%S%f')}-{uuid4().hex[:8]}"

    report_dir = canonical_root / "apifox" / "reports" / "runs" / date_str / run_id
    nodes_dir = report_dir / "nodes"
    resolved_logs_path = Path(logs_path).resolve()
    resolved_log_paths = {
        name: Path(path).resolve()
        for name, path in (log_paths or _infer_log_paths(resolved_logs_path)).items()
    }
    nodes_dir.mkdir(parents=True, exist_ok=True)
    resolved_logs_path.parent.mkdir(parents=True, exist_ok=True)

    report = RunReport(
        path=report_dir,
        summary_path=report_dir / "summary.yaml",
        tree_path=report_dir / "tree.txt",
        console_path=report_dir / "console.log",
        nodes_path=nodes_dir,
        logs_path=resolved_logs_path,
        log_paths=resolved_log_paths,
        run_id=run_id,
        date=date_str,
    )

    summary_payload = {
        "kind": "runReport",
        "generatedAt": generated_at.isoformat(),
        "resource": {"kind": kind, "id": resource_id},
        "summary": _summary_counts(summary),
        "details": list(summary.get("details") or []),
        "report": report.to_payload(),
    }
    _write_yaml(report.summary_path, summary_payload)
    report.tree_path.write_text("\n".join(_build_tree_lines(kind, resource_id, summary)) + "\n", encoding="utf-8")

    for index, detail in enumerate(summary_payload["details"], start=1):
        detail_id = str(detail.get("resource_id") or resource_id)
        node_name = f"{index:03d}-{_sanitize_filename(detail_id)}.yaml"
        _write_yaml(report.nodes_path / node_name, detail)

    write_console_log(report, console_lines)
    return report


def _infer_log_paths(logs_path: Path) -> Dict[str, Path]:
    name = logs_path.name.lower()
    if name.startswith("error-"):
        return {"error": logs_path}
    if name.startswith("warning-"):
        return {"warning": logs_path}
    return {"info": logs_path}
