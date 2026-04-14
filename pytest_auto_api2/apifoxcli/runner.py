from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .assertions import assert_response
from .context import RunContext
from .contract import build_case_request, validate_case_contract
from .extractor import apply_extractors
from .models import ExpectSpec, ExtractSpec
from .planner import build_api_plan, build_case_plan, build_flow_plan, build_suite_plan
from .transport.http import execute_http_api


@dataclass
class RunSummary:
    total: int = 0
    passed: int = 0
    failed: int = 0
    details: List[Dict[str, Any]] = field(default_factory=list)


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


def _execute_api_node(project, node, contexts: Dict[str, RunContext]) -> Dict[str, object]:
    api = project.apis[node.resource_id]
    context = _build_or_get_context(project, node, contexts)
    response = execute_http_api(api, context)
    assert_response(api.spec.expect, response, context.values)
    apply_extractors(api.spec.extract, response, context)
    return {"resource_id": node.resource_id, "status_code": response.status_code}


def _execute_case_node(project, node, contexts: Dict[str, RunContext]) -> Dict[str, object]:
    case = project.cases[node.resource_id]
    api = project.apis[case.spec.apiRef]
    context = _build_or_get_context(project, node, contexts)
    contract_errors = validate_case_contract(case, api)
    if contract_errors:
        raise AssertionError("; ".join(contract_errors))

    prepared = build_case_request(case, api, context)
    response = execute_http_api(prepared, context)
    expect = ExpectSpec.model_validate(case.spec.expect)
    extractors = [ExtractSpec.model_validate(item) for item in case.spec.extract]
    assert_response(expect, response, context.values)
    apply_extractors(extractors, response, context)
    return {"resource_id": node.resource_id, "status_code": response.status_code}
