from __future__ import annotations

from typing import List

from .models import LoadedProject
from .resolver import iter_expression_tokens

SUPPORTED_PREFIXES = ("env.", "context.", "dataset.", "fn.")


def _validate_supported_expressions(owner: str, value, errors: List[str]) -> None:
    for token in iter_expression_tokens(value):
        if not token.startswith(SUPPORTED_PREFIXES):
            errors.append(f"{owner} unsupported expression: {token}")

def validate_project(project: LoadedProject) -> List[str]:
    errors: List[str] = []

    if project.project.spec.defaultEnv not in project.envs:
        errors.append(f"project.defaultEnv not found: {project.project.spec.defaultEnv}")

    for env in project.envs.values():
        _validate_supported_expressions(f"env {env.id}", env.spec.headers, errors)

    for api in project.apis.values():
        env_ref = api.spec.envRef or project.project.spec.defaultEnv
        if env_ref not in project.envs:
            errors.append(f"api {api.id} envRef not found: {env_ref}")

        if api.spec.request:
            for _, field_value in (
                ("headers", api.spec.request.headers),
                ("query", api.spec.request.query),
                ("json", api.spec.request.json_body),
                ("form", api.spec.request.form),
            ):
                _validate_supported_expressions(f"api {api.id}", field_value, errors)

    for case in project.cases.values():
        if case.spec.apiRef not in project.apis:
            errors.append(f"case {case.id} apiRef not found: {case.spec.apiRef}")

        env_ref = case.spec.envRef or project.project.spec.defaultEnv
        if env_ref not in project.envs:
            errors.append(f"case {case.id} envRef not found: {env_ref}")
        _validate_supported_expressions(f"case {case.id}", case.spec.request, errors)

    for flow in project.flows.values():
        for step_index, step in enumerate(flow.spec.steps):
            ref_count = int(bool(step.caseRef)) + int(bool(step.apiRef))
            if ref_count != 1:
                errors.append(
                    f"flow {flow.id} step {step_index} must define exactly one of caseRef or apiRef"
                )
            if step.caseRef and step.caseRef not in project.cases:
                errors.append(f"flow {flow.id} caseRef not found: {step.caseRef}")
            if step.apiRef and step.apiRef not in project.apis:
                errors.append(f"flow {flow.id} apiRef not found: {step.apiRef}")

    for suite in project.suites.values():
        for item_index, item in enumerate(suite.spec.items):
            ref_count = int(bool(item.caseRef)) + int(bool(item.apiRef)) + int(bool(item.flowRef))
            if ref_count != 1:
                errors.append(
                    f"suite {suite.id} item {item_index} must define exactly one of caseRef, apiRef, or flowRef"
                )
            if item.caseRef and item.caseRef not in project.cases:
                errors.append(f"suite {suite.id} caseRef not found: {item.caseRef}")
            if item.apiRef and item.apiRef not in project.apis:
                errors.append(f"suite {suite.id} apiRef not found: {item.apiRef}")
            if item.flowRef and item.flowRef not in project.flows:
                errors.append(f"suite {suite.id} flowRef not found: {item.flowRef}")
            if item.datasetRef and item.datasetRef not in project.datasets:
                errors.append(f"suite {suite.id} datasetRef not found: {item.datasetRef}")

    return errors
