from pytest_auto_api2.apifoxcli.loader import load_project
from pytest_auto_api2.apifoxcli.source_sync import (
    normalize_openapi_document,
    plan_source_sync,
)


def test_plan_source_sync_detects_created_updated_and_removed_api(tmp_path):
    apifox = tmp_path / "apifox"
    for rel in ("sources", "envs", "apis"):
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
    (apifox / "apis" / "auth" / "login.yaml").parent.mkdir(parents=True, exist_ok=True)
    (apifox / "apis" / "auth" / "login.yaml").write_text(
        "kind: api\nid: auth.login\nname: Login\nmeta:\n  module: auth\n  tags:\n    - 登录模块\n  sync:\n    sourceId: demo-openapi\n    syncKey: login_post\n    upstreamMethod: POST\n    upstreamPath: /login\n    lifecycle: active\nspec:\n  protocol: http\n  contract:\n    request:\n      method: POST\n      path: /login\n      contentType: application/x-www-form-urlencoded\n      formSchema:\n        username:\n          type: string\n          required: true\n        password:\n          type: string\n          required: true\n    responses:\n      '200': {}\n",
        encoding="utf-8",
    )
    (apifox / "apis" / "auth" / "removed.yaml").write_text(
        "kind: api\nid: auth.removed\nname: Removed\nmeta:\n  module: auth\n  tags:\n    - 登录模块\n  sync:\n    sourceId: demo-openapi\n    syncKey: removed_get\n    upstreamMethod: GET\n    upstreamPath: /removed\n    lifecycle: active\nspec:\n  protocol: http\n  contract:\n    request:\n      method: GET\n      path: /removed\n      contentType: application/json\n    responses:\n      '200': {}\n",
        encoding="utf-8",
    )

    project = load_project(tmp_path)
    document = {
        "openapi": "3.0.3",
        "paths": {
            "/login": {
                "post": {
                    "operationId": "login_post",
                    "summary": "Login",
                    "tags": ["登录模块"],
                    "requestBody": {
                        "content": {
                            "application/x-www-form-urlencoded": {
                                "schema": {
                                    "type": "object",
                                    "required": ["username", "password", "tenantId"],
                                    "properties": {
                                        "username": {"type": "string"},
                                        "password": {"type": "string"},
                                        "tenantId": {"type": "string"},
                                    },
                                }
                            }
                        }
                    },
                    "responses": {"200": {"description": "ok"}},
                }
            },
            "/getInfo": {
                "get": {
                    "operationId": "get_info_get",
                    "summary": "Get Info",
                    "tags": ["登录模块"],
                    "responses": {"200": {"description": "ok"}},
                }
            },
        },
    }

    normalized = normalize_openapi_document(project.sources["demo-openapi"], document)
    plan = plan_source_sync(project, "demo-openapi", normalized)

    assert [item.api_id for item in plan.created] == ["auth.get-info"]
    assert [item.api_id for item in plan.updated] == ["auth.login"]
    assert [item.api_id for item in plan.upstream_removed] == ["auth.removed"]
    assert plan.updated[0].diffs[0].kind == "request.requiredAdded"
    assert plan.updated[0].diffs[0].field == "tenantId"
