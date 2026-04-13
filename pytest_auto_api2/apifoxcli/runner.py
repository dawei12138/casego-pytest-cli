from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .assertions import assert_response
from .context import RunContext
from .extractor import apply_extractors
from .planner import build_api_plan, build_suite_plan
from .transport.http import execute_http_api


@dataclass
class RunSummary:
    total: int = 0
    passed: int = 0
    failed: int = 0
    details: List[Dict[str, Any]] = field(default_factory=list)


def run_api(project, api_id: str, env_override: Optional[str] = None) -> RunSummary:
    plan = build_api_plan(project, api_id, env_override)
    return _execute_plan(project, plan)


def run_suite(project, suite_id: str, env_override: Optional[str] = None) -> RunSummary:
    plan = build_suite_plan(project, suite_id, env_override)
    return _execute_plan(project, plan)


def _execute_plan(project, plan) -> RunSummary:
    summary = RunSummary(total=len(plan.nodes))

    for node in plan.nodes:
        api = project.apis[node.resource_id]
        env = project.envs[node.env_id].spec.model_dump()
        context = RunContext(env=env, dataset=node.dataset)

        try:
            response = execute_http_api(api, context)
            assert_response(api.spec.expect, response, context.values)
            apply_extractors(api.spec.extract, response, context)
        except Exception as exc:
            summary.failed += 1
            summary.details.append({"resource_id": node.resource_id, "error": str(exc)})
            if plan.fail_fast:
                break
            continue

        summary.passed += 1
        summary.details.append({"resource_id": node.resource_id, "status_code": response.status_code})

    return summary
