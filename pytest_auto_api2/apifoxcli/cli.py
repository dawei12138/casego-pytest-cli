from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

from .loader import load_project
from .execution_log import emit_execution_log
from .openapi_importer import bootstrap_openapi_source, load_openapi_document
from .resource_store import (
    append_flow_step,
    append_suite_item,
    case_file,
    flow_file,
    get_env_variable,
    list_env_variables,
    require_project_initialized,
    resource_file,
    set_env_header,
    set_env_variable,
    set_project_default_env,
    suite_file,
    unset_env_variable,
    write_case,
    write_env,
    write_flow,
    write_suite,
)
from .run_reports import write_console_log, write_run_report
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
from pytest_auto_api2.utils.logging_tool.log_control import temporary_runtime_loggers

_RESOURCE_COLLECTIONS = {
    "api": "apis",
    "case": "cases",
    "flow": "flows",
    "suite": "suites",
    "source": "sources",
    "env": "envs",
    "dataset": "datasets",
}

_RUN_COMMAND_HINTS = {
    "api": "api send",
    "case": "case send",
    "flow": "flow run",
    "suite": "suite run",
}


def _cmd_not_implemented(_args: argparse.Namespace) -> int:
    return 2


def _cmd_project_init(args: argparse.Namespace) -> int:
    init_project(Path(args.project_root), name=args.name, default_env=args.default_env)
    return 0


def _cmd_env_create(args: argparse.Namespace) -> int:
    write_env(Path(args.project_root), args.env_id, base_url=args.base_url, name=args.env_id)
    return 0


def _cmd_env_use(args: argparse.Namespace) -> int:
    set_project_default_env(Path(args.project_root), args.env_id)
    return 0


def _cmd_env_var_set(args: argparse.Namespace) -> int:
    set_env_variable(Path(args.project_root), args.env_id, args.key, args.value)
    return 0


def _cmd_env_var_get(args: argparse.Namespace) -> int:
    value = get_env_variable(Path(args.project_root), args.env_id, args.key)
    if isinstance(value, str):
        print(value)
    else:
        _emit_json(value)
    return 0


def _cmd_env_var_list(args: argparse.Namespace) -> int:
    _emit_json(list_env_variables(Path(args.project_root), args.env_id))
    return 0


def _cmd_env_var_unset(args: argparse.Namespace) -> int:
    unset_env_variable(Path(args.project_root), args.env_id, args.key)
    return 0


def _cmd_env_header_set(args: argparse.Namespace) -> int:
    set_env_header(Path(args.project_root), args.env_id, args.key, args.value)
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
    if prune and not apply:
        raise ValueError("source sync --prune requires --apply")
    project = load_project(project_root)
    source = project.sources[source_id]
    loaded_document = document if document is not None else load_openapi_document(source.spec.url, root=project.root)
    normalized = normalize_openapi_document(source, loaded_document)
    plan = plan_source_sync(project, source_id, normalized)
    report = (
        apply_source_sync(project, source_id, plan, prune=prune)
        if apply
        else build_sync_report(project, source_id, plan)
    )
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


def _emit_execution_logs(summary) -> None:
    payload = _summary_to_payload(summary)
    for item in payload.get("details", []):
        emit_execution_log(item)


def _assert_resource_type(project, expected_kind: str, resource_id: str) -> None:
    expected_collection = getattr(project, _RESOURCE_COLLECTIONS[expected_kind], {})
    if resource_id in expected_collection:
        return

    for resource_kind, collection_name in _RESOURCE_COLLECTIONS.items():
        if resource_kind == expected_kind:
            continue
        collection = getattr(project, collection_name, {})
        if resource_id not in collection:
            continue
        hint = _RUN_COMMAND_HINTS.get(resource_kind)
        if hint:
            raise ValueError(f"resource '{resource_id}' is a {resource_kind}; use: apifoxcli {hint} {resource_id}")
        raise ValueError(f"resource '{resource_id}' is a {resource_kind}, not a {expected_kind}")

    raise ValueError(f"{expected_kind} not found: {resource_id}")


def _render_text_value(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def _build_text_run_summary_lines(kind: str, resource_id: str, summary, *, verbose: bool = False, report=None) -> List[str]:
    payload = _summary_to_payload(summary)
    outcome = "PASS" if int(payload.get("failed", 0)) == 0 else "FAIL"
    lines = [
        f"{outcome} {kind} {resource_id} "
        f"total={payload.get('total', 0)} passed={payload.get('passed', 0)} failed={payload.get('failed', 0)}"
    ]
    for item in payload.get("details", []):
        detail_id = str(item.get("resource_id") or resource_id)
        request = item.get("request") or {}
        parts = [f"- {detail_id}"]
        env_id = item.get("env_id")
        if env_id:
            parts.append(f"env={env_id}")
        method = request.get("method")
        url = request.get("url")
        if method and url:
            parts.append(f"{method} {url}")
        if "status_code" in item and item.get("status_code") is not None:
            parts.append(f"status={item['status_code']}")
        if "error" in item:
            parts.append(f"error={item['error']}")
        lines.append(" ".join(parts))

        show_extra = verbose or "error" in item
        if not show_extra:
            continue

        dataset = item.get("dataset", {})
        if verbose or dataset not in (None, {}, []):
            lines.append(f"  dataset={_render_text_value(dataset)}")
        headers = request.get("headers", {})
        if verbose or headers not in (None, {}, []):
            lines.append(f"  request.headers={_render_text_value(headers)}")
        query = request.get("query", {})
        if verbose or query not in (None, {}, []):
            lines.append(f"  request.query={_render_text_value(query)}")
        json_payload = request.get("json")
        if verbose or json_payload not in (None, {}, []):
            lines.append(f"  request.json={_render_text_value(json_payload)}")
        form_payload = request.get("form", {})
        if verbose or form_payload not in (None, {}, []):
            lines.append(f"  request.form={_render_text_value(form_payload)}")

        response = item.get("response") or {}
        if response.get("body") not in (None, "", {}, []):
            lines.append(f"  response.body={_render_text_value(response['body'])}")

    if report is not None:
        lines.append(f"report: {report.path}")
        lines.append(f"logs:   {report.logs_path}")
        extra_log_paths = {
            name: path
            for name, path in getattr(report, "log_paths", {}).items()
            if Path(path) != Path(report.logs_path)
        }
        for name, path in sorted(extra_log_paths.items()):
            lines.append(f"logs.{name}: {path}")

    return lines


def _emit_text_lines(lines: List[str]) -> None:
    for line in lines:
        print(line)


def _build_run_payload(summary, report=None):
    payload = _summary_to_payload(summary)
    if report is None:
        return payload
    enriched = dict(payload)
    enriched["report"] = report.to_payload()
    return enriched


def _detail_uses_error_log(item: Dict[str, object]) -> bool:
    if "error" in item:
        return True
    status_code = item.get("status_code")
    if status_code is None:
        status_code = (item.get("response") or {}).get("status_code")
    if status_code is None:
        return False
    try:
        return int(status_code) >= 400
    except (TypeError, ValueError):
        return False


def _used_log_paths(summary, bound_paths: Dict[str, Path]) -> Dict[str, Path]:
    payload = _summary_to_payload(summary)
    used: Dict[str, Path] = {}
    for item in payload.get("details", []):
        key = "error" if _detail_uses_error_log(item) else "info"
        used[key] = Path(bound_paths[key])
    if used:
        return used
    fallback_key = "error" if int(payload.get("failed", 0) or 0) > 0 else "info"
    return {fallback_key: Path(bound_paths[fallback_key])}


def _bind_run_logs(project, summary) -> Dict[str, object]:
    project_root = Path(getattr(project, "root", ".")).resolve()
    with temporary_runtime_loggers(project_root) as bound_paths:
        _emit_execution_logs(summary)
        used_paths = _used_log_paths(summary, bound_paths)
    primary_key = "error" if "error" in used_paths else next(iter(used_paths))
    return {
        "primary": Path(used_paths[primary_key]),
        "paths": {name: Path(path) for name, path in used_paths.items()},
    }


def _prepare_run_output(
    project,
    kind: str,
    resource_id: str,
    summary,
    *,
    logs_path: Path,
    log_paths: Dict[str, Path],
    verbose: bool = False,
):
    payload = _summary_to_payload(summary)
    project_root = Path(getattr(project, "root", "."))
    report = write_run_report(
        project_root=project_root,
        kind=kind,
        resource_id=resource_id,
        summary=payload,
        console_lines=[],
        logs_path=logs_path,
        log_paths=log_paths,
    )
    text_lines = _build_text_run_summary_lines(kind, resource_id, payload, verbose=verbose, report=report)
    if hasattr(report, "console_path"):
        write_console_log(report, text_lines)
    return payload, report, text_lines


def _cmd_api_send(args: argparse.Namespace) -> int:
    project = load_project(Path(args.project_root))
    _assert_resource_type(project, "api", args.resource_id)
    summary = run_api(project, args.resource_id, args.env, args.dataset)
    log_meta = _bind_run_logs(project, summary)
    _, report, text_lines = _prepare_run_output(
        project,
        "api",
        args.resource_id,
        summary,
        logs_path=log_meta["primary"],
        log_paths=log_meta["paths"],
        verbose=bool(getattr(args, "verbose", False)),
    )
    if args.json:
        _emit_json(_build_run_payload(summary, report))
    else:
        _emit_text_lines(text_lines)
    return 0 if summary.failed == 0 else 1


def _cmd_case_run(args: argparse.Namespace) -> int:
    project = load_project(Path(args.project_root))
    _assert_resource_type(project, "case", args.resource_id)
    summary = run_case(project, args.resource_id, args.env, args.dataset)
    log_meta = _bind_run_logs(project, summary)
    _, report, text_lines = _prepare_run_output(
        project,
        "case",
        args.resource_id,
        summary,
        logs_path=log_meta["primary"],
        log_paths=log_meta["paths"],
        verbose=bool(getattr(args, "verbose", False)),
    )
    if args.json:
        _emit_json(_build_run_payload(summary, report))
    else:
        _emit_text_lines(text_lines)
    return 0 if summary.failed == 0 else 1


def _cmd_case_create(args: argparse.Namespace) -> int:
    project_root = Path(args.project_root)
    project = load_project(project_root)
    _assert_resource_type(project, "api", args.from_api)
    if args.case_id in project.cases or case_file(project_root, args.case_id).exists():
        raise FileExistsError(f"case already exists: {args.case_id}")

    api = project.apis[args.from_api]
    request_snapshot = (
        api.spec.request.model_dump(by_alias=True, exclude_none=True)
        if api.spec.request is not None
        else {}
    )
    write_case(
        project_root,
        args.case_id,
        api_ref=args.from_api,
        request=request_snapshot,
        name=args.case_id,
    )
    return 0


def _cmd_flow_create(args: argparse.Namespace) -> int:
    project_root = Path(args.project_root)
    require_project_initialized(project_root)
    if flow_file(project_root, args.flow_id).exists():
        raise FileExistsError(f"flow already exists: {args.flow_id}")
    write_flow(project_root, args.flow_id, name=args.flow_id)
    return 0


def _cmd_flow_add(args: argparse.Namespace) -> int:
    project_root = Path(args.project_root)
    require_project_initialized(project_root)
    if not flow_file(project_root, args.flow_id).exists():
        raise FileNotFoundError(f"flow not found: {args.flow_id}")
    if args.case_id is not None and not case_file(project_root, args.case_id).exists():
        raise FileNotFoundError(f"case not found: {args.case_id}")
    if args.api_id is not None and not resource_file(project_root, "apis", args.api_id).exists():
        raise FileNotFoundError(f"api not found: {args.api_id}")
    append_flow_step(project_root, args.flow_id, case_ref=args.case_id, api_ref=args.api_id)
    return 0


def _cmd_flow_run(args: argparse.Namespace) -> int:
    project = load_project(Path(args.project_root))
    _assert_resource_type(project, "flow", args.resource_id)
    summary = run_flow(project, args.resource_id, args.env, args.dataset)
    log_meta = _bind_run_logs(project, summary)
    _, report, text_lines = _prepare_run_output(
        project,
        "flow",
        args.resource_id,
        summary,
        logs_path=log_meta["primary"],
        log_paths=log_meta["paths"],
        verbose=bool(getattr(args, "verbose", False)),
    )
    if args.json:
        _emit_json(_build_run_payload(summary, report))
    else:
        _emit_text_lines(text_lines)
    return 0 if summary.failed == 0 else 1


def _cmd_suite_create(args: argparse.Namespace) -> int:
    project_root = Path(args.project_root)
    require_project_initialized(project_root)
    if suite_file(project_root, args.suite_id).exists():
        raise FileExistsError(f"suite already exists: {args.suite_id}")
    write_suite(project_root, args.suite_id, name=args.suite_id)
    return 0


def _cmd_suite_add(args: argparse.Namespace) -> int:
    project_root = Path(args.project_root)
    require_project_initialized(project_root)
    if not suite_file(project_root, args.suite_id).exists():
        raise FileNotFoundError(f"suite not found: {args.suite_id}")
    if args.case_id is not None and not case_file(project_root, args.case_id).exists():
        raise FileNotFoundError(f"case not found: {args.case_id}")
    if args.api_id is not None and not resource_file(project_root, "apis", args.api_id).exists():
        raise FileNotFoundError(f"api not found: {args.api_id}")
    if args.flow_ref is not None and not flow_file(project_root, args.flow_ref).exists():
        raise FileNotFoundError(f"flow not found: {args.flow_ref}")
    if args.dataset_id is not None and not resource_file(project_root, "datasets", args.dataset_id).exists():
        raise FileNotFoundError(f"dataset not found: {args.dataset_id}")
    append_suite_item(
        project_root,
        args.suite_id,
        case_ref=args.case_id,
        api_ref=args.api_id,
        flow_ref=args.flow_ref,
        dataset_ref=args.dataset_id,
    )
    return 0


def _cmd_suite_run(args: argparse.Namespace) -> int:
    project = load_project(Path(args.project_root))
    _assert_resource_type(project, "suite", args.resource_id)
    summary = run_suite(project, args.resource_id, args.env)
    log_meta = _bind_run_logs(project, summary)
    _, report, text_lines = _prepare_run_output(
        project,
        "suite",
        args.resource_id,
        summary,
        logs_path=log_meta["primary"],
        log_paths=log_meta["paths"],
        verbose=bool(getattr(args, "verbose", False)),
    )
    if args.json:
        _emit_json(_build_run_payload(summary, report))
    else:
        _emit_text_lines(text_lines)
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
    project_init.add_argument("--name", required=True)
    project_init.add_argument("--default-env", default="qa")
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

    env_parser = sub.add_parser("env")
    env_sub = env_parser.add_subparsers(dest="action", required=True)

    env_create = env_sub.add_parser("create")
    env_create.add_argument("env_id")
    env_create.add_argument("--base-url", required=True)
    env_create.add_argument("--project-root", default=".")
    env_create.set_defaults(handler=_cmd_env_create)

    env_use = env_sub.add_parser("use")
    env_use.add_argument("env_id")
    env_use.add_argument("--project-root", default=".")
    env_use.set_defaults(handler=_cmd_env_use)

    env_var = env_sub.add_parser("var")
    env_var_sub = env_var.add_subparsers(dest="var_action", required=True)

    env_var_set = env_var_sub.add_parser("set")
    env_var_set.add_argument("env_id")
    env_var_set.add_argument("key")
    env_var_set.add_argument("value")
    env_var_set.add_argument("--project-root", default=".")
    env_var_set.set_defaults(handler=_cmd_env_var_set)

    env_var_get = env_var_sub.add_parser("get")
    env_var_get.add_argument("env_id")
    env_var_get.add_argument("key")
    env_var_get.add_argument("--project-root", default=".")
    env_var_get.set_defaults(handler=_cmd_env_var_get)

    env_var_list = env_var_sub.add_parser("list")
    env_var_list.add_argument("env_id")
    env_var_list.add_argument("--project-root", default=".")
    env_var_list.set_defaults(handler=_cmd_env_var_list)

    env_var_unset = env_var_sub.add_parser("unset")
    env_var_unset.add_argument("env_id")
    env_var_unset.add_argument("key")
    env_var_unset.add_argument("--project-root", default=".")
    env_var_unset.set_defaults(handler=_cmd_env_var_unset)

    env_header = env_sub.add_parser("header")
    env_header_sub = env_header.add_subparsers(dest="header_action", required=True)

    env_header_set = env_header_sub.add_parser("set")
    env_header_set.add_argument("env_id")
    env_header_set.add_argument("key")
    env_header_set.add_argument("value")
    env_header_set.add_argument("--project-root", default=".")
    env_header_set.set_defaults(handler=_cmd_env_header_set)

    api_parser = sub.add_parser("api")
    api_sub = api_parser.add_subparsers(dest="action", required=True)
    api_send = api_sub.add_parser("send")
    api_send.add_argument("resource_id")
    api_send.add_argument("--project-root", default=".")
    api_send.add_argument("--env", default=None)
    api_send.add_argument("--dataset", default=None)
    api_send.add_argument("--verbose", action="store_true")
    api_send.add_argument("--json", action="store_true")
    api_send.set_defaults(handler=_cmd_api_send)

    case_parser = sub.add_parser("case")
    case_sub = case_parser.add_subparsers(dest="action", required=True)
    case_run = case_sub.add_parser("run")
    case_run.add_argument("resource_id")
    case_run.add_argument("--project-root", default=".")
    case_run.add_argument("--env", default=None)
    case_run.add_argument("--dataset", default=None)
    case_run.add_argument("--verbose", action="store_true")
    case_run.add_argument("--json", action="store_true")
    case_run.set_defaults(handler=_cmd_case_run)
    case_send = case_sub.add_parser("send")
    case_send.add_argument("resource_id")
    case_send.add_argument("--project-root", default=".")
    case_send.add_argument("--env", default=None)
    case_send.add_argument("--dataset", default=None)
    case_send.add_argument("--verbose", action="store_true")
    case_send.add_argument("--json", action="store_true")
    case_send.set_defaults(handler=_cmd_case_run)
    case_create = case_sub.add_parser("create")
    case_create.add_argument("case_id")
    case_create.add_argument("--from-api", required=True)
    case_create.add_argument("--project-root", default=".")
    case_create.set_defaults(handler=_cmd_case_create)

    flow_parser = sub.add_parser("flow")
    flow_sub = flow_parser.add_subparsers(dest="action", required=True)
    flow_create = flow_sub.add_parser("create")
    flow_create.add_argument("flow_id")
    flow_create.add_argument("--project-root", default=".")
    flow_create.set_defaults(handler=_cmd_flow_create)
    flow_add = flow_sub.add_parser("add")
    flow_add.add_argument("flow_id")
    flow_add.add_argument("--project-root", default=".")
    flow_add_target = flow_add.add_mutually_exclusive_group(required=True)
    flow_add_target.add_argument("--case", dest="case_id")
    flow_add_target.add_argument("--api", dest="api_id")
    flow_add.set_defaults(handler=_cmd_flow_add)
    flow_run = flow_sub.add_parser("run")
    flow_run.add_argument("resource_id")
    flow_run.add_argument("--project-root", default=".")
    flow_run.add_argument("--env", default=None)
    flow_run.add_argument("--dataset", default=None)
    flow_run.add_argument("--verbose", action="store_true")
    flow_run.add_argument("--json", action="store_true")
    flow_run.set_defaults(handler=_cmd_flow_run)

    suite_parser = sub.add_parser("suite")
    suite_sub = suite_parser.add_subparsers(dest="action", required=True)
    suite_create = suite_sub.add_parser("create")
    suite_create.add_argument("suite_id")
    suite_create.add_argument("--project-root", default=".")
    suite_create.set_defaults(handler=_cmd_suite_create)
    suite_add = suite_sub.add_parser("add")
    suite_add.add_argument("suite_id")
    suite_add.add_argument("--project-root", default=".")
    suite_add_target = suite_add.add_mutually_exclusive_group(required=True)
    suite_add_target.add_argument("--case", dest="case_id")
    suite_add_target.add_argument("--api", dest="api_id")
    suite_add_target.add_argument("--flow", dest="flow_ref")
    suite_add.add_argument("--dataset", dest="dataset_id", default=None)
    suite_add.set_defaults(handler=_cmd_suite_add)
    suite_run = suite_sub.add_parser("run")
    suite_run.add_argument("resource_id")
    suite_run.add_argument("--project-root", default=".")
    suite_run.add_argument("--env", default=None)
    suite_run.add_argument("--verbose", action="store_true")
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
