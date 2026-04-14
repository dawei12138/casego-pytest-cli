from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, TYPE_CHECKING
from uuid import uuid4

import yaml

from .models import LoadedProject

if TYPE_CHECKING:
    from .source_sync import SyncPlan


@dataclass
class SyncReport:
    source_id: str
    summary: Dict[str, int]
    details: Dict[str, List[str]]
    impacts: Dict[str, object] = field(default_factory=dict)
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_payload(self) -> Dict[str, object]:
        return {
            "kind": "syncReport",
            "sourceId": self.source_id,
            "generatedAt": self.generated_at,
            "summary": self.summary,
            "details": self.details,
            "impacts": self.impacts,
        }


def build_sync_report(
    _project: LoadedProject,
    source_id: str,
    plan: SyncPlan,
    *,
    impact: Optional[object] = None,
    pruned_api_ids: Optional[List[str]] = None,
) -> SyncReport:
    impact_cases = list(getattr(impact, "cases", []) or [])
    impact_flows = list(getattr(impact, "flows", []) or [])
    impact_suites = list(getattr(impact, "suites", []) or [])
    pruned_api_ids = pruned_api_ids or []
    return SyncReport(
        source_id=source_id,
        summary={
            "createdApis": len(plan.created),
            "updatedApis": len(plan.updated),
            "upstreamRemovedApis": len(plan.upstream_removed),
            "unchangedApis": len(plan.unchanged),
            "impactedCases": len(impact_cases),
            "impactedFlows": len(impact_flows),
            "impactedSuites": len(impact_suites),
            "prunedApis": len(pruned_api_ids),
        },
        details={
            "createdApis": [item.api_id for item in plan.created],
            "updatedApis": [item.api_id for item in plan.updated],
            "upstreamRemovedApis": [item.api_id for item in plan.upstream_removed],
            "unchangedApis": [item.api_id for item in plan.unchanged],
            "impactedCases": [entry["caseId"] for entry in impact_cases if isinstance(entry.get("caseId"), str)],
            "impactedFlows": [entry["flowId"] for entry in impact_flows if isinstance(entry.get("flowId"), str)],
            "impactedSuites": [
                entry["suiteId"] for entry in impact_suites if isinstance(entry.get("suiteId"), str)
            ],
            "prunedApis": list(pruned_api_ids),
        },
        impacts={
            "cases": impact_cases,
            "flows": impact_flows,
            "suites": impact_suites,
        },
    )


def write_sync_report(root: Path, report: SyncReport) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    file_name = f"{report.source_id}-{stamp}-{uuid4().hex[:8]}.yaml"
    path = root / file_name
    path.write_text(yaml.safe_dump(report.to_payload(), allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path
