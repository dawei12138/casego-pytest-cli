#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Case cache loader for generated tests and dependency resolution."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Optional

from common.setting import data_dir_path, resolve_project_path
from utils.cache_process.cache_control import CacheHandler, _cache_config
from utils.read_files_tools.get_yaml_data_analysis import CaseData

_CACHE_BUILT = False


def _iter_yaml_files(data_dir: Path) -> Iterable[Path]:
    for pattern in ("*.yaml", "*.yml"):
        for path in data_dir.rglob(pattern):
            if path.is_file() and path.name != "proxy_data.yaml":
                yield path


def build_case_cache(data_dir: Optional[str] = None, *, force: bool = False) -> int:
    """Load all yaml case definitions into the in-memory cache."""
    global _CACHE_BUILT

    if _CACHE_BUILT and not force:
        return len(_cache_config)

    target = resolve_project_path(data_dir) if data_dir else data_dir_path()
    data_root = Path(target)
    if not data_root.exists():
        raise FileNotFoundError(f"YAML data directory does not exist: {data_root}")

    if force:
        _cache_config.clear()

    seen_case_ids = set(_cache_config.keys())
    for yaml_path in _iter_yaml_files(data_root):
        case_process = CaseData(str(yaml_path)).case_process(case_id_switch=True)
        if not case_process:
            continue

        for case in case_process:
            for case_id, case_data in case.items():
                if case_id in seen_case_ids:
                    raise ValueError(
                        f"Duplicate case_id detected: {case_id}\nfile: {yaml_path}"
                    )
                CacheHandler.update_cache(cache_name=case_id, value=case_data)
                seen_case_ids.add(case_id)

    _CACHE_BUILT = True
    return len(seen_case_ids)


def load_cases_by_ids(case_ids: List[str], *, data_dir: Optional[str] = None) -> List[dict]:
    """Return parsed case data list in the same order as incoming ids."""
    build_case_cache(data_dir=data_dir)

    cases: List[dict] = []
    missing = []
    for case_id in case_ids:
        if case_id not in _cache_config:
            missing.append(case_id)
            continue
        cases.append(_cache_config[case_id])

    if missing:
        raise KeyError(f"Case ids not found in cache: {missing}")

    return cases


def clear_case_cache() -> None:
    """Clear in-memory cache and reset build flag."""
    global _CACHE_BUILT
    _cache_config.clear()
    _CACHE_BUILT = False
