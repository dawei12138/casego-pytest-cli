from __future__ import annotations

from typing import Dict, List, Optional

from .context import ExecutionPlan, PlanNode
from .models import LoadedProject


def _expand_dataset(project: LoadedProject, dataset_ref: Optional[str]) -> List[Dict[str, object]]:
    if not dataset_ref:
        return [{}]
    return list(project.datasets[dataset_ref].spec.rows) or [{}]


def _build_flow_nodes(
    project: LoadedProject,
    flow_id: str,
    env_id: str,
    dataset: Dict[str, object],
    context_key: str,
) -> List[PlanNode]:
    flow = project.flows[flow_id]
    return [
        PlanNode(
            kind="api",
            resource_id=step.apiRef,
            env_id=env_id,
            dataset=dict(dataset),
            context_key=context_key,
        )
        for step in flow.spec.steps
    ]


def build_api_plan(
    project: LoadedProject,
    api_id: str,
    env_override: Optional[str],
    dataset_ref: Optional[str] = None,
) -> ExecutionPlan:
    api = project.apis[api_id]
    env_id = env_override or api.spec.envRef or project.project.spec.defaultEnv
    rows = _expand_dataset(project, dataset_ref)
    return ExecutionPlan(
        nodes=[
            PlanNode(
                kind="api",
                resource_id=api_id,
                env_id=env_id,
                dataset=row,
                context_key=f"api:{api_id}:{row_index}",
            )
            for row_index, row in enumerate(rows)
        ]
    )


def build_flow_plan(
    project: LoadedProject,
    flow_id: str,
    env_override: Optional[str],
    dataset_ref: Optional[str] = None,
) -> ExecutionPlan:
    flow = project.flows[flow_id]
    env_id = env_override or flow.spec.envRef or project.project.spec.defaultEnv
    nodes: List[PlanNode] = []
    for row_index, row in enumerate(_expand_dataset(project, dataset_ref)):
        nodes.extend(_build_flow_nodes(project, flow_id, env_id, row, f"flow:{flow_id}:{row_index}"))
    return ExecutionPlan(nodes=nodes)


def build_suite_plan(project: LoadedProject, suite_id: str, env_override: Optional[str]) -> ExecutionPlan:
    suite = project.suites[suite_id]
    env_id = env_override or suite.spec.envRef or project.project.spec.defaultEnv
    nodes: List[PlanNode] = []

    for item_index, item in enumerate(suite.spec.items):
        if item.apiRef:
            for row_index, row in enumerate(_expand_dataset(project, item.datasetRef)):
                nodes.append(
                    PlanNode(
                        kind="api",
                        resource_id=item.apiRef,
                        env_id=env_id,
                        dataset=row,
                        context_key=f"suite:{suite_id}:item:{item_index}:row:{row_index}:api",
                    )
                )
        elif item.flowRef:
            for row_index, row in enumerate(_expand_dataset(project, item.datasetRef)):
                context_key = f"suite:{suite_id}:item:{item_index}:row:{row_index}:flow"
                nodes.extend(_build_flow_nodes(project, item.flowRef, env_id, row, context_key))

    return ExecutionPlan(nodes=nodes, fail_fast=suite.spec.failFast)
