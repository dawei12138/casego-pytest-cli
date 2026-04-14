from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

from .loader import load_project
from .openapi_importer import bootstrap_openapi_source, load_openapi_document
from .runner import run_api, run_case, run_flow, run_suite
from .scaffold import init_project
from .source_sync import (
    apply_source_sync,
    normalize_openapi_document,
    plan_source_sync,
    read_latest_sync_report,
    upsert_source_rebind,
)
from .sync_report import build_sync_report
from .validator import validate_project


def _cmd_not_implemented(_args: argparse.Namespace) -> int:
    return 2


def _cmd_project_init(args: argparse.Namespace) -> int:
    init_project(Path(args.project_root))
    return 0


def _cmd_project_import_openapi(args: argparse.Namespace) -> int:
    project_root = Path(args.project_root)
    document = load_openapi_document(args.source, root=project_root)
    bootstrap_openapi_source(
        root=project_root,
        source_id=args.source_id,
        source=args.source,
        env_id=args.env_id,
        server_description=args.server_description,
        server_url=args.server_url,
        include_paths=args.include_path,
        document=document,
    )
    return _run_source_sync(
        project_root=project_root,
        source_id=args.source_id,
        apply=True,
        prune=False,
        json_output=getattr(args, "json", False),
        document=document,
    )


def _run_source_sync(
    *,
    project_root: Path,
    source_id: str,
    apply: bool,
    prune: bool,
    json_output: bool,
    document: Optional[Dict[str, object]] = None,
) -> int:
    if prune:
        raise NotImplementedError("source sync --prune is not implemented yet")
    project = load_project(project_root)
    source = project.sources[source_id]
    loaded_document = document if document is not None else load_openapi_document(source.spec.url, root=project.root)
    normalized = normalize_openapi_document(source, loaded_document)
    plan = plan_source_sync(project, source_id, normalized)
    report = apply_source_sync(project, source_id, plan) if apply else build_sync_report(project, source_id, plan)
    if json_output:
        _emit_json(report)
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    project = load_project(Path(args.project_root))
    errors = validate_project(project)
    if errors:
        for item in errors:
            print(f"validate error: {item}")
        return 2
    print("validate ok")
    return 0


def _summary_to_payload(summary):
    if isinstance(summary, dict):
        return summary
    if hasattr(summary, "to_payload"):
        return summary.to_payload()
    if all(hasattr(summary, attr) for attr in ("total", "passed", "failed", "details")):
        return {
            "total": summary.total,
            "passed": summary.passed,
            "failed": summary.failed,
            "details": summary.details,
        }
    return summary


def _emit_json(summary) -> None:
    print(
        json.dumps(
            _summary_to_payload(summary),
            ensure_ascii=False,
        )
    )


def _emit_error_json(exc: Exception) -> None:
    _emit_json({"error": {"type": exc.__class__.__name__, "message": str(exc)}})


def _cmd_api_send(args: argparse.Namespace) -> int:
    project = load_project(Path(args.project_root))
    summary = run_api(project, args.resource_id, args.env, args.dataset)
    if args.json:
        _emit_json(summary)
    return 0 if summary.failed == 0 else 1


def _cmd_case_run(args: argparse.Namespace) -> int:
    project = load_project(Path(args.project_root))
    summary = run_case(project, args.resource_id, args.env, args.dataset)
    if args.json:
        _emit_json(summary)
    return 0 if summary.failed == 0 else 1


def _cmd_flow_run(args: argparse.Namespace) -> int:
    project = load_project(Path(args.project_root))
    summary = run_flow(project, args.resource_id, args.env, args.dataset)
    if args.json:
        _emit_json(summary)
    return 0 if summary.failed == 0 else 1


def _cmd_suite_run(args: argparse.Namespace) -> int:
    project = load_project(Path(args.project_root))
    summary = run_suite(project, args.resource_id, args.env)
    if args.json:
        _emit_json(summary)
    return 0 if summary.failed == 0 else 1


def _cmd_source_sync(args: argparse.Namespace) -> int:
    return _run_source_sync(
        project_root=Path(args.project_root),
        source_id=args.resource_id,
        apply=bool(args.apply),
        prune=bool(getattr(args, "prune", False)),
        json_output=bool(getattr(args, "json", False)),
    )


def _cmd_source_status(args: argparse.Namespace) -> int:
    report = read_latest_sync_report(Path(args.project_root), args.resource_id)
    if args.json:
        _emit_json(report)
    return 0


def _cmd_source_rebind(args: argparse.Namespace) -> int:
    upsert_source_rebind(Path(args.project_root), args.resource_id, args.api_id, args.sync_key)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="apifoxcli")
    sub = parser.add_subparsers(dest="resource", required=True)

    project_parser = sub.add_parser("project")
    project_sub = project_parser.add_subparsers(dest="action", required=True)
    project_init = project_sub.add_parser("init")
    project_init.add_argument("--project-root", default=".")
    project_init.set_defaults(handler=_cmd_project_init)
    project_import = project_sub.add_parser("import-openapi")
    project_import.add_argument("--project-root", default=".")
    project_import.add_argument("--source", required=True)
    project_import.add_argument("--env-id", default="qa")
    project_import.add_argument("--source-id", default="openapi")
    project_import.add_argument("--server-description", default=None)
    project_import.add_argument("--server-url", default=None)
    project_import.add_argument("--include-path", action="append", default=[])
    project_import.add_argument("--json", action="store_true")
    project_import.set_defaults(handler=_cmd_project_import_openapi)

    validate_parser = sub.add_parser("validate")
    validate_parser.add_argument("--project-root", default=".")
    validate_parser.set_defaults(resource="validate", action="run", handler=_cmd_validate)

    api_parser = sub.add_parser("api")
    api_sub = api_parser.add_subparsers(dest="action", required=True)
    api_send = api_sub.add_parser("send")
    api_send.add_argument("resource_id")
    api_send.add_argument("--project-root", default=".")
    api_send.add_argument("--env", default=None)
    api_send.add_argument("--dataset", default=None)
    api_send.add_argument("--json", action="store_true")
    api_send.set_defaults(handler=_cmd_api_send)

    case_parser = sub.add_parser("case")
    case_sub = case_parser.add_subparsers(dest="action", required=True)
    case_run = case_sub.add_parser("run")
    case_run.add_argument("resource_id")
    case_run.add_argument("--project-root", default=".")
    case_run.add_argument("--env", default=None)
    case_run.add_argument("--dataset", default=None)
    case_run.add_argument("--json", action="store_true")
    case_run.set_defaults(handler=_cmd_case_run)

    flow_parser = sub.add_parser("flow")
    flow_sub = flow_parser.add_subparsers(dest="action", required=True)
    flow_run = flow_sub.add_parser("run")
    flow_run.add_argument("resource_id")
    flow_run.add_argument("--project-root", default=".")
    flow_run.add_argument("--env", default=None)
    flow_run.add_argument("--dataset", default=None)
    flow_run.add_argument("--json", action="store_true")
    flow_run.set_defaults(handler=_cmd_flow_run)

    suite_parser = sub.add_parser("suite")
    suite_sub = suite_parser.add_subparsers(dest="action", required=True)
    suite_run = suite_sub.add_parser("run")
    suite_run.add_argument("resource_id")
    suite_run.add_argument("--project-root", default=".")
    suite_run.add_argument("--env", default=None)
    suite_run.add_argument("--json", action="store_true")
    suite_run.set_defaults(handler=_cmd_suite_run)

    source_parser = sub.add_parser("source")
    source_sub = source_parser.add_subparsers(dest="action", required=True)
    source_sync = source_sub.add_parser("sync")
    source_sync.add_argument("resource_id")
    source_sync.add_argument("--project-root", default=".")
    source_sync_mode = source_sync.add_mutually_exclusive_group()
    source_sync_mode.add_argument("--apply", action="store_true")
    source_sync_mode.add_argument("--plan", action="store_true")
    source_sync.add_argument("--prune", action="store_true")
    source_sync.add_argument("--json", action="store_true")
    source_sync.set_defaults(handler=_cmd_source_sync)

    source_status = source_sub.add_parser("status")
    source_status.add_argument("resource_id")
    source_status.add_argument("--project-root", default=".")
    source_status.add_argument("--json", action="store_true")
    source_status.set_defaults(handler=_cmd_source_status)

    source_rebind = source_sub.add_parser("rebind")
    source_rebind.add_argument("resource_id")
    source_rebind.add_argument("--project-root", default=".")
    source_rebind.add_argument("--api-id", required=True)
    source_rebind.add_argument("--sync-key", required=True)
    source_rebind.set_defaults(handler=_cmd_source_rebind)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        return args.handler(args)
    except Exception as exc:
        if "args" in locals() and bool(getattr(args, "json", False)):
            _emit_error_json(exc)
        else:
            print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
