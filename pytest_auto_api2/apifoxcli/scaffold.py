from __future__ import annotations

from pathlib import Path

from .resource_store import (
    ensure_apifox_layout,
    env_file,
    write_env,
    write_project,
    write_scaffold_smoke_suite,
)


def init_project(root: Path, *, name: str, default_env: str = "qa") -> None:
    env_file(root, default_env)
    ensure_apifox_layout(root)
    write_project(root, name=name, default_env=default_env)
    if not env_file(root, default_env).exists():
        write_env(root, default_env, base_url="http://127.0.0.1:8000", name=default_env)
    write_scaffold_smoke_suite(root, env_ref=default_env)
