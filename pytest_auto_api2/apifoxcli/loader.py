from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable

import yaml

from .models import (
    ApiResource,
    DatasetResource,
    EnvResource,
    FlowResource,
    LoadedProject,
    ProjectResource,
    SuiteResource,
)


def _read_yaml(path: Path) -> Dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise TypeError(f"YAML root must be a mapping: {path}")
    return data


def _iter_yaml_files(path: Path) -> Iterable[Path]:
    if not path.exists():
        return []
    return path.rglob("*.yaml")


def load_project(root: Path) -> LoadedProject:
    project_root = Path(root)
    apifox = project_root / "apifox"
    project = ProjectResource(**_read_yaml(apifox / "project.yaml"))
    loaded = LoadedProject(root=project_root, project=project)

    for path in _iter_yaml_files(apifox / "envs"):
        resource = EnvResource(**_read_yaml(path))
        loaded.envs[resource.id] = resource
    for path in _iter_yaml_files(apifox / "apis"):
        resource = ApiResource(**_read_yaml(path))
        loaded.apis[resource.id] = resource
    for path in _iter_yaml_files(apifox / "flows"):
        resource = FlowResource(**_read_yaml(path))
        loaded.flows[resource.id] = resource
    for path in _iter_yaml_files(apifox / "suites"):
        resource = SuiteResource(**_read_yaml(path))
        loaded.suites[resource.id] = resource
    for path in _iter_yaml_files(apifox / "datasets"):
        resource = DatasetResource(**_read_yaml(path))
        loaded.datasets[resource.id] = resource

    return loaded
