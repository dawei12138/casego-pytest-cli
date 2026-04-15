from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .assertions import assert_response
from .context import RunContext
from .contract import build_case_request, validate_case_contract
from .extractor import apply_extractors
from .models import ExpectSpec, ExtractSpec
from .planner import build_api_plan, build_case_plan, build_flow_plan, build_suite_plan
from .transport.http import (
    build_http_request_url,
    execute_prepared_http_request,
    prepare_http_api_request,
)


@dataclass
class RunSummary:
    total: int = 0
    passed: int = 0
    failed: int = 0
    details: List[Dict[str, Any]] = field(default_factory=list)


class NodeExecutionError(Exception):
    def __init__(self, detail: Dict[str, Any]):
        self.detail = detail
        super().__init__(str(detail.get("error") or "node execution failed"))


def run_api(project, api_id: str, env_override: Optional[str] = None, dataset_ref: Optional[str] = None) -> RunSummary:
    plan = build_api_plan(project, api_id, env_override, dataset_ref)
    return _execute_plan(project, plan)


def run_case(
    project, case_id: str, env_override: Optional[str] = None, dataset_ref: Optional[str] = None
) -> RunSummary:
    plan = build_case_plan(project, case_id, env_override, dataset_ref)
    return _execute_plan(project, plan)


def run_flow(project, flow_id: str, env_override: Optional[str] = None, dataset_ref: Optional[str] = None) -> RunSummary:
    plan = build_flow_plan(project, flow_id, env_override, dataset_ref)
    return _execute_plan(project, plan)


def run_suite(project, suite_id: str, env_override: Optional[str] = None) -> RunSummary:
    plan = build_suite_plan(project, suite_id, env_override)
    return _execute_plan(project, plan)


def _execute_plan(project, plan) -> RunSummary:
    summary = RunSummary(total=len(plan.nodes))
    contexts: Dict[str, RunContext] = {}

    for node in plan.nodes:
        try:
            if node.kind == "case":
                detail = _execute_case_node(project, node, contexts)
            else:
                detail = _execute_api_node(project, node, contexts)
        except NodeExecutionError as exc:
            summary.failed += 1
            summary.details.append(exc.detail)
            if plan.fail_fast:
                break
            continue
        except Exception as exc:
            summary.failed += 1
            summary.details.append({"resource_id": node.resource_id, "error": str(exc)})
            if plan.fail_fast:
                break
            continue

        summary.passed += 1
        summary.details.append(detail)

    return summary


def _build_or_get_context(project, node, contexts: Dict[str, RunContext]) -> RunContext:
    context = contexts.get(node.context_key)
    if context is None:
        env = project.envs[node.env_id].spec.model_dump()
        context = RunContext(env=env, dataset=node.dataset)
        contexts[node.context_key] = context
    else:
        context.dataset = node.dataset
    return context


def _compact_snapshot(value):
    if value is None:
        return None
    if isinstance(value, dict):
        return {key: item for key, item in value.items() if item not in (None, "")}
    return value


def _response_body_preview(response):
    try:
        payload = response.json()
        return payload
    except Exception:
        text = response.text or ""
        if not text:
            return None
        return text if len(text) <= 1000 else f"{text[:997]}..."


def _build_request_detail(prepared, context, env_id: str) -> Dict[str, object]:
    return {
        "env_id": env_id,
        "request": {
            "method": prepared.method,
            "url": build_http_request_url(prepared, context),
            "headers": _compact_snapshot(prepared.headers or {}) or {},
            "query": _compact_snapshot(prepared.query or {}) or {},
            "json": prepared.json_body,
            "form": _compact_snapshot(prepared.form or {}) or {},
        },
    }


def _attach_response_detail(detail: Dict[str, Any], response) -> None:
    detail["status_code"] = response.status_code
    elapsed = getattr(response, "elapsed", None)
    elapsed_ms = None
    if elapsed is not None:
        try:
            elapsed_ms = round(float(elapsed.total_seconds()) * 1000, 2)
        except Exception:
            elapsed_ms = None
    detail["elapsed_ms"] = elapsed_ms
    detail["response"] = {
        "status_code": response.status_code,
        "body": _response_body_preview(response),
    }


def _execute_api_node(project, node, contexts: Dict[str, RunContext]) -> Dict[str, object]:
    api = project.apis[node.resource_id]
    context = _build_or_get_context(project, node, contexts)
    prepared = prepare_http_api_request(api, context)
    detail: Dict[str, Any] = {
        "resource_id": node.resource_id,
        "title": api.name,
        "dataset": dict(context.dataset),
        **_build_request_detail(prepared, context, node.env_id),
    }
    response = None
    try:
        response = execute_prepared_http_request(prepared, context)
        _attach_response_detail(detail, response)
        assert_response(api.spec.expect, response, context.values)
        apply_extractors(api.spec.extract, response, context)
        return detail
    except Exception as exc:
        if response is not None and "response" not in detail:
            _attach_response_detail(detail, response)
        detail["error"] = str(exc)
        raise NodeExecutionError(detail)


def _execute_case_node(project, node, contexts: Dict[str, RunContext]) -> Dict[str, object]:
    case = project.cases[node.resource_id]
    api = project.apis[case.spec.apiRef]
    context = _build_or_get_context(project, node, contexts)
    detail: Dict[str, Any] = {
        "resource_id": node.resource_id,
        "title": case.name,
        "api_id": case.spec.apiRef,
        "dataset": dict(context.dataset),
    }
    response = None
    try:
        contract_errors = validate_case_contract(case, api)
        if contract_errors:
            raise AssertionError("; ".join(contract_errors))

        prepared = build_case_request(case, api, context)
        detail.update(_build_request_detail(prepared, context, node.env_id))
        response = execute_prepared_http_request(prepared, context)
        _attach_response_detail(detail, response)
        expect = ExpectSpec.model_validate(case.spec.expect)
        extractors = [ExtractSpec.model_validate(item) for item in case.spec.extract]
        assert_response(expect, response, context.values)
        apply_extractors(extractors, response, context)
        return detail
    except Exception as exc:
        if response is not None and "response" not in detail:
            _attach_response_detail(detail, response)
        detail["error"] = str(exc)
        raise NodeExecutionError(detail)
