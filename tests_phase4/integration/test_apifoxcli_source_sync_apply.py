import yaml

from pytest_auto_api2.apifoxcli.loader import load_project
from pytest_auto_api2.apifoxcli.source_sync import apply_source_sync, normalize_openapi_document, plan_source_sync


def test_apply_source_sync_writes_tag_modules_and_marks_removed_without_touching_cases(tmp_path):
    apifox = tmp_path / "apifox"
    for rel in ("sources", "envs", "apis", "cases", "reports/sync"):
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
        "kind: api\nid: auth.post.login\nname: Login\nmeta:\n  module: auth\n  tags:\n    - 登录模块\n  sync:\n    sourceId: demo-openapi\n    syncKey: login_post\n    lifecycle: active\nspec:\n  protocol: http\n  contract:\n    request:\n      method: POST\n      path: /login\n      contentType: application/x-www-form-urlencoded\n      formSchema:\n        username:\n          type: string\n          required: true\n        password:\n          type: string\n          required: true\n    responses:\n      '200': {}\n",
        encoding="utf-8",
    )
    (apifox / "cases" / "login-success.yaml").write_text(
        "kind: case\nid: auth.login.success\nname: login success\nmeta:\n  audit:\n    status: healthy\n    reasons: []\nspec:\n  apiRef: auth.post.login\n  request:\n    form:\n      username: guest\n      password: 123456\n  expect:\n    status: 200\n    assertions: []\n  extract: []\n",
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
            }
        },
    }

    normalized = normalize_openapi_document(project.sources["demo-openapi"], document)
    plan = plan_source_sync(project, "demo-openapi", normalized)
    report = apply_source_sync(project, "demo-openapi", plan)

    login_yaml = yaml.safe_load((apifox / "apis" / "auth" / "login.yaml").read_text(encoding="utf-8"))
    case_yaml = yaml.safe_load((apifox / "cases" / "login-success.yaml").read_text(encoding="utf-8"))
    assert login_yaml["meta"]["module"] == "auth"
    assert login_yaml["meta"]["sync"]["lifecycle"] == "active"
    assert "tenantId" in login_yaml["spec"]["contract"]["request"]["formSchema"]
    assert case_yaml["spec"]["request"]["form"] == {"username": "guest", "password": 123456}
    assert report.summary["updatedApis"] == 1
    assert (apifox / "reports" / "sync").exists()


def test_apply_source_sync_marks_upstream_removed_and_keeps_api_file(tmp_path):
    apifox = tmp_path / "apifox"
    for rel in ("sources", "envs", "apis", "reports/sync"):
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
    (apifox / "apis" / "auth").mkdir(parents=True, exist_ok=True)
    (apifox / "apis" / "auth" / "login.yaml").write_text(
        "kind: api\nid: auth.post.login\nname: Login\nmeta:\n  module: auth\n  sync:\n    sourceId: demo-openapi\n    syncKey: login_post\n    lifecycle: active\nspec:\n  protocol: http\n  contract:\n    request:\n      method: POST\n      path: /login\n      contentType: application/json\n    responses:\n      '200': {}\n",
        encoding="utf-8",
    )
    (apifox / "apis" / "auth" / "stale.yaml").write_text(
        "kind: api\nid: auth.get.stale\nname: stale\nmeta:\n  module: auth\n  sync:\n    sourceId: demo-openapi\n    syncKey: stale_get\n    lifecycle: active\nspec:\n  protocol: http\n  contract:\n    request:\n      method: GET\n      path: /stale\n      contentType: application/json\n    responses:\n      '200': {}\n",
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
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    }

    normalized = normalize_openapi_document(project.sources["demo-openapi"], document)
    plan = plan_source_sync(project, "demo-openapi", normalized)
    apply_source_sync(project, "demo-openapi", plan)

    stale_yaml = yaml.safe_load((apifox / "apis" / "auth" / "stale.yaml").read_text(encoding="utf-8"))
    assert stale_yaml["meta"]["sync"]["lifecycle"] == "upstreamRemoved"
