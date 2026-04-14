from pathlib import Path

import pytest
import yaml

from pytest_auto_api2.apifoxcli.loader import load_project
from pytest_auto_api2.apifoxcli.source_sync import (
    analyze_sync_impact,
    apply_source_sync,
    normalize_openapi_document,
    plan_source_sync,
)


def _read_yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_sync_impact_marks_case_flow_suite_and_blocks_prune_for_referenced_api(tmp_path):
    apifox = tmp_path / "apifox"
    for rel in ("sources", "envs", "apis", "cases", "flows", "suites"):
        (apifox / rel).mkdir(parents=True, exist_ok=True)

    (apifox / "project.yaml").write_text(
        "kind: project\nid: default\nname: demo\nspec:\n  defaultEnv: qa\n",
        encoding="utf-8",
    )
    (apifox / "sources" / "demo-openapi.yaml").write_text(
        "kind: source\nid: demo-openapi\nname: demo\nspec:\n  type: openapi\n  url: https://demo.example/openapi.json\n  syncMode: full\n  includePaths: []\n  excludePaths: []\n  tagMap:\n    登录模块: auth\n  guards:\n    maxRemoveCount: 20\n    maxRemoveRatio: 0.2\n",
        encoding="utf-8",
    )
    (apifox / "envs" / "qa.yaml").write_text(
        "kind: env\nid: qa\nname: QA\nspec:\n  baseUrl: https://demo.example/dev-api\n  headers: {}\n  variables: {}\n",
        encoding="utf-8",
    )
    (apifox / "apis" / "auth-get-user.yaml").write_text(
        "kind: api\nid: auth.post.user\nname: Create User\nmeta:\n  module: auth\n  sync:\n    sourceId: demo-openapi\n    syncKey: post_user_post\n    lifecycle: active\nspec:\n  protocol: http\n  contract:\n    request:\n      method: POST\n      path: /user\n      contentType: application/x-www-form-urlencoded\n      formSchema:\n        tenantId:\n          type: string\n          required: true\n    responses:\n      '200': {}\n",
        encoding="utf-8",
    )
    (apifox / "cases" / "user-smoke.yaml").write_text(
        "kind: case\nid: auth.user.smoke\nname: user smoke\nmeta:\n  audit:\n    status: healthy\n    reasons: []\nspec:\n  apiRef: auth.post.user\n  request:\n    form: {}\n  expect:\n    status: 200\n    assertions: []\n  extract: []\n",
        encoding="utf-8",
    )
    (apifox / "flows" / "bootstrap.yaml").write_text(
        "kind: flow\nid: auth.bootstrap\nname: bootstrap\nspec:\n  steps:\n    - caseRef: auth.user.smoke\n",
        encoding="utf-8",
    )
    (apifox / "suites" / "smoke.yaml").write_text(
        "kind: suite\nid: smoke\nname: smoke\nspec:\n  items:\n    - flowRef: auth.bootstrap\n",
        encoding="utf-8",
    )

    project = load_project(tmp_path)
    document = {
        "openapi": "3.0.3",
        "paths": {
            "/user": {
                "post": {
                    "operationId": "post_user_post",
                    "summary": "Get User",
                    "tags": ["登录模块"],
                    "requestBody": {
                        "content": {
                            "application/x-www-form-urlencoded": {
                                "schema": {
                                    "type": "object",
                                    "required": ["tenantId", "region"],
                                    "properties": {
                                        "tenantId": {"type": "string"},
                                        "region": {"type": "string"},
                                    },
                                }
                            }
                        }
                    },
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    }

    normalized = normalize_openapi_document(project.sources["demo-openapi"], document)
    plan = plan_source_sync(project, "demo-openapi", normalized)
    original_case_spec = _read_yaml(apifox / "cases" / "user-smoke.yaml")["spec"]
    impact = analyze_sync_impact(project, plan)

    assert impact.cases[0]["caseId"] == "auth.user.smoke"
    assert impact.cases[0]["reasons"][0]["type"] == "missing_required_input"
    assert impact.flows[0]["flowId"] == "auth.bootstrap"
    assert impact.suites[0]["suiteId"] == "smoke"
    assert project.cases["auth.user.smoke"].meta["audit"]["status"] == "healthy"

    report = apply_source_sync(project, "demo-openapi", plan, prune=True)
    assert report.summary["prunedApis"] == 0
    assert report.summary["impactedCases"] == 1

    case_yaml = _read_yaml(apifox / "cases" / "user-smoke.yaml")
    assert case_yaml["spec"] == original_case_spec
    assert case_yaml["spec"]["apiRef"] == "auth.post.user"
    assert case_yaml["meta"]["audit"]["status"] == "impacted"
    assert case_yaml["meta"]["audit"]["reasons"][0]["type"] == "missing_required_input"


def test_apply_source_sync_prunes_unreferenced_upstream_removed_api_when_prune_enabled(tmp_path):
    apifox = tmp_path / "apifox"
    for rel in ("sources", "envs", "apis", "cases", "flows", "suites"):
        (apifox / rel).mkdir(parents=True, exist_ok=True)

    (apifox / "project.yaml").write_text(
        "kind: project\nid: default\nname: demo\nspec:\n  defaultEnv: qa\n",
        encoding="utf-8",
    )
    (apifox / "sources" / "demo-openapi.yaml").write_text(
        "kind: source\nid: demo-openapi\nname: demo\nspec:\n  type: openapi\n  url: https://demo.example/openapi.json\n  syncMode: full\n  includePaths: []\n  excludePaths: []\n  tagMap:\n    AuthTag: auth\n  guards:\n    maxRemoveCount: 20\n    maxRemoveRatio: 1.0\n",
        encoding="utf-8",
    )
    (apifox / "envs" / "qa.yaml").write_text(
        "kind: env\nid: qa\nname: QA\nspec:\n  baseUrl: https://demo.example/dev-api\n  headers: {}\n  variables: {}\n",
        encoding="utf-8",
    )
    stale_path = apifox / "apis" / "auth" / "stale.yaml"
    stale_path.parent.mkdir(parents=True, exist_ok=True)
    stale_path.write_text(
        "kind: api\nid: auth.get.stale\nname: stale\nmeta:\n  module: auth\n  sync:\n    sourceId: demo-openapi\n    syncKey: stale_get\n    lifecycle: active\nspec:\n  protocol: http\n  contract:\n    request:\n      method: GET\n      path: /stale\n      contentType: application/json\n    responses:\n      '200': {}\n",
        encoding="utf-8",
    )

    project = load_project(tmp_path)
    normalized = normalize_openapi_document(project.sources["demo-openapi"], {"openapi": "3.0.3", "paths": {}})
    plan = plan_source_sync(project, "demo-openapi", normalized)
    report = apply_source_sync(project, "demo-openapi", plan, prune=True)

    assert report.summary["upstreamRemovedApis"] == 1
    assert report.summary["prunedApis"] == 1
    assert report.details["prunedApis"] == ["auth.get.stale"]
    assert not stale_path.exists()


def test_apply_source_sync_prune_ratio_guard_blocks_even_when_count_guard_allows(tmp_path):
    apifox = tmp_path / "apifox"
    for rel in ("sources", "envs", "apis", "cases", "flows", "suites"):
        (apifox / rel).mkdir(parents=True, exist_ok=True)

    (apifox / "project.yaml").write_text(
        "kind: project\nid: default\nname: demo\nspec:\n  defaultEnv: qa\n",
        encoding="utf-8",
    )
    (apifox / "sources" / "demo-openapi.yaml").write_text(
        "kind: source\nid: demo-openapi\nname: demo\nspec:\n  type: openapi\n  url: https://demo.example/openapi.json\n  syncMode: full\n  includePaths: []\n  excludePaths: []\n  tagMap:\n    AuthTag: auth\n  guards:\n    maxRemoveCount: 20\n    maxRemoveRatio: 0.0\n",
        encoding="utf-8",
    )
    (apifox / "envs" / "qa.yaml").write_text(
        "kind: env\nid: qa\nname: QA\nspec:\n  baseUrl: https://demo.example/dev-api\n  headers: {}\n  variables: {}\n",
        encoding="utf-8",
    )
    stale_path = apifox / "apis" / "auth" / "stale.yaml"
    stale_path.parent.mkdir(parents=True, exist_ok=True)
    stale_path.write_text(
        "kind: api\nid: auth.get.stale\nname: stale\nmeta:\n  module: auth\n  sync:\n    sourceId: demo-openapi\n    syncKey: stale_get\n    lifecycle: active\nspec:\n  protocol: http\n  contract:\n    request:\n      method: GET\n      path: /stale\n      contentType: application/json\n    responses:\n      '200': {}\n",
        encoding="utf-8",
    )

    project = load_project(tmp_path)
    normalized = normalize_openapi_document(project.sources["demo-openapi"], {"openapi": "3.0.3", "paths": {}})
    plan = plan_source_sync(project, "demo-openapi", normalized)

    with pytest.raises(ValueError) as exc_info:
        apply_source_sync(project, "demo-openapi", plan, prune=True)

    assert "maxRemoveRatio" in str(exc_info.value)
    assert stale_path.exists()
