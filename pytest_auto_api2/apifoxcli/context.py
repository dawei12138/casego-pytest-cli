from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class RunContext:
    env: Dict[str, Any]
    dataset: Dict[str, Any]
    values: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PlanNode:
    kind: str
    resource_id: str
    env_id: str
    dataset: Dict[str, Any]
    context_key: str


@dataclass
class ExecutionPlan:
    nodes: List[PlanNode]
    fail_fast: bool = False
