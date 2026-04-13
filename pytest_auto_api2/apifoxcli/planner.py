from __future__ import annotations

from typing import Dict, List, Optional

from .context import ExecutionPlan, PlanNode
from .models import LoadedProject


def _expand_dataset(project: LoadedProject, dataset_ref: Optional[str]) -> List[Dict[str, object]]:
    if not dataset_ref:
        return [{}]
    return list(project.datasets[dataset_ref].spec.rows) or [{}]


def build_api_plan(project: LoadedProject, api_id: str, env_override: Optional[str]) -> ExecutionPlan:
    api = project.apis[api_id]
    env_id = env_override or api.spec.envRef or project.project.spec.defaultEnv
    return ExecutionPlan(nodes=[PlanNode(kind="api", resource_id=api_id, env_id=env_id, dataset={})])


def build_suite_plan(project: LoadedProject, suite_id: str, env_override: Optional[str]) -> ExecutionPlan:
    suite = project.suites[suite_id]
    env_id = env_override or suite.spec.envRef or project.project.spec.defaultEnv
    nodes: List[PlanNode] = []

    for item in suite.spec.items:
        if item.apiRef:
            for row in _expand_dataset(project, item.datasetRef):
                nodes.append(PlanNode(kind="api", resource_id=item.apiRef, env_id=env_id, dataset=row))
        elif item.flowRef:
            nodes.append(PlanNode(kind="flow", resource_id=item.flowRef, env_id=env_id, dataset={}))

    return ExecutionPlan(nodes=nodes, fail_fast=suite.spec.failFast)
