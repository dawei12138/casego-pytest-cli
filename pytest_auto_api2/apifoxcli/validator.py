from __future__ import annotations

import re
from typing import Any, Iterable
from typing import List

from .models import LoadedProject

SUPPORTED_PREFIXES = ("env.", "context.", "dataset.", "fn.")
TOKEN_RE = re.compile(r"\$\{([^}]+)\}")


def _iter_string_values(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
        return
    if isinstance(value, dict):
        for item in value.values():
            yield from _iter_string_values(item)
        return
    if isinstance(value, list):
        for item in value:
            yield from _iter_string_values(item)


def validate_project(project: LoadedProject) -> List[str]:
    errors: List[str] = []

    if project.project.spec.defaultEnv not in project.envs:
        errors.append(f"project.defaultEnv not found: {project.project.spec.defaultEnv}")

    for api in project.apis.values():
        env_ref = api.spec.envRef or project.project.spec.defaultEnv
        if env_ref not in project.envs:
            errors.append(f"api {api.id} envRef not found: {env_ref}")

        for field_name in ("headers", "query", "json", "form"):
            field_value = getattr(api.spec.request, field_name)
            for raw in _iter_string_values(field_value):
                for token in TOKEN_RE.findall(raw):
                    if not token.startswith(SUPPORTED_PREFIXES):
                        errors.append(f"api {api.id} unsupported expression: {token}")

    for flow in project.flows.values():
        for step in flow.spec.steps:
            if step.apiRef not in project.apis:
                errors.append(f"flow {flow.id} apiRef not found: {step.apiRef}")

    for suite in project.suites.values():
        for item in suite.spec.items:
            if item.apiRef and item.apiRef not in project.apis:
                errors.append(f"suite {suite.id} apiRef not found: {item.apiRef}")
            if item.flowRef and item.flowRef not in project.flows:
                errors.append(f"suite {suite.id} flowRef not found: {item.flowRef}")
            if item.datasetRef and item.datasetRef not in project.datasets:
                errors.append(f"suite {suite.id} datasetRef not found: {item.datasetRef}")

    return errors
