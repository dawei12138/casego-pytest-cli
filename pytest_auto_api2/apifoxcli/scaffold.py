from __future__ import annotations

from pathlib import Path


def init_project(root: Path) -> None:
    apifox = root / "apifox"
    for rel in ("sources", "envs", "apis", "cases", "flows", "suites", "datasets", "mocks"):
        (apifox / rel).mkdir(parents=True, exist_ok=True)

    files = {
        apifox / "project.yaml": "kind: project\nid: default\nname: demo project\nspec:\n  defaultEnv: qa\n",
        apifox / "envs" / "qa.yaml": "kind: env\nid: qa\nname: QA\nspec:\n  baseUrl: http://127.0.0.1:8000\n  headers: {}\n  variables: {}\n",
        apifox / "suites" / "smoke.yaml": "kind: suite\nid: smoke\nname: Smoke\nspec:\n  envRef: qa\n  failFast: true\n  concurrency: 1\n  items: []\n",
    }
    for path, content in files.items():
        if not path.exists():
            path.write_text(content, encoding="utf-8")
