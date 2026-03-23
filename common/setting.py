#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time   : 2021/11/25 13:07
# @Author : 浣欏皯鐞?

import os
from typing import Text

PROJECT_ROOT_ENV = "PYTEST_AUTO_API2_HOME"
CONFIG_PATH_ENV = "PYTEST_AUTO_API2_CONFIG"
DATA_DIR_ENV = "PYTEST_AUTO_API2_DATA_DIR"
TEST_DIR_ENV = "PYTEST_AUTO_API2_TEST_DIR"


def _normalize_sep(path: Text) -> Text:
    """Normalize path separators for current OS."""
    if "/" in path:
        path = os.sep.join(path.split("/"))
    if "\\" in path:
        path = os.sep.join(path.split("\\"))
    return path


def root_path() -> Text:
    """Return project root path."""
    env_root = os.getenv(PROJECT_ROOT_ENV)
    if env_root:
        return os.path.abspath(env_root)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resolve_project_path(path: Text) -> Text:
    """Resolve absolute path with project root as base for relative values."""
    if path is None:
        return root_path()
    normalized = _normalize_sep(str(path))
    if os.path.isabs(normalized):
        return os.path.abspath(normalized)
    return os.path.abspath(os.path.join(root_path(), normalized))


def ensure_path_sep(path: Text) -> Text:
    """Build absolute path under project root while preserving compatibility."""
    normalized = _normalize_sep(path)
    drive, _ = os.path.splitdrive(normalized)

    # Keep historical behavior: `\`-prefixed paths are project-root relative.
    if normalized.startswith(os.sep) and not drive:
        return os.path.abspath(root_path() + normalized)

    if os.path.isabs(normalized):
        return os.path.abspath(normalized)

    return os.path.abspath(os.path.join(root_path(), normalized))


def config_path() -> Text:
    """Return active config path."""
    env_config = os.getenv(CONFIG_PATH_ENV)
    if env_config:
        return resolve_project_path(env_config)
    return ensure_path_sep("\\common\\config.yaml")


def data_dir_path() -> Text:
    """Return active yaml data directory."""
    env_data = os.getenv(DATA_DIR_ENV)
    if env_data:
        return resolve_project_path(env_data)
    return ensure_path_sep("\\data")


def test_case_dir_path() -> Text:
    """Return active generated test directory."""
    env_test = os.getenv(TEST_DIR_ENV)
    if env_test:
        return resolve_project_path(env_test)
    return ensure_path_sep("\\test_case")