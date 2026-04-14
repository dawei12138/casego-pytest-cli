from pathlib import Path

import yaml

from pytest_auto_api2.apifoxcli.loader import load_project
from pytest_auto_api2.apifoxcli.source_sync import apply_source_sync, normalize_openapi_document, plan_source_sync


def _read_yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _write_text(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _create_base_project(apifox: Path):
    for rel in ("sources", "envs", "apis", "cases", "reports/sync"):
        (apifox / rel).mkdir(parents=True, exist_ok=True)
    _write_text(
        apifox / "project.yaml",
        "kind: project\nid: default\nname: demo\nspec:\n  defaultEnv: qa\n",
    )
    _write_text(
        apifox / "sources" / "demo-openapi.yaml",
        "kind: source\nid: demo-openapi\nname: demo\nspec:\n  type: openapi\n  url: https://demo.example/openapi.json\n  syncMode: full\n  includePaths: []\n  excludePaths: []\n  tagMap:\n    AuthTag: auth\n  guards:\n    maxRemoveCount: 20\n    maxRemoveRatio: 0.2\n",
    )
    _write_text(
        apifox / "envs" / "qa.yaml",
        "kind: env\nid: qa\nname: QA\nspec:\n  baseUrl: https://demo.example/dev-api\n  headers: {}\n  variables: {}\n",
    )


def _find_api_payload(root: Path, api_id: str):
    for file_path in sorted(root.rglob("*.yaml")):
        payload = _read_yaml(file_path)
        if payload.get("id") == api_id:
            return payload, file_path
    raise AssertionError(f"api yaml not found for id: {api_id}")


def test_apply_source_sync_writes_created_updated_removed_and_report_without_touching_cases(tmp_path):
    apifox = tmp_path / "apifox"
    _create_base_project(apifox)
    _write_text(
        apifox / "apis" / "auth" / "login.yaml",
        "kind: api\nid: auth.post.login\nname: Login\nmeta:\n  module: auth\n  tags:\n    - AuthTag\n  sync:\n    sourceId: demo-openapi\n    syncKey: login_post\n    lifecycle: active\nspec:\n  protocol: http\n  contract:\n    request:\n      method: POST\n      path: /login\n      contentType: application/x-www-form-urlencoded\n      formSchema:\n        username:\n          type: string\n          required: true\n        password:\n          type: string\n          required: true\n    responses:\n      '200': {}\n",
    )
    _write_text(
        apifox / "apis" / "auth" / "stale.yaml",
        "kind: api\nid: auth.get.stale\nname: stale\nmeta:\n  module: auth\n  sync:\n    sourceId: demo-openapi\n    syncKey: stale_get\n    lifecycle: active\nspec:\n  protocol: http\n  contract:\n    request:\n      method: GET\n      path: /stale\n      contentType: application/json\n    responses:\n      '200': {}\n",
    )
    _write_text(
        apifox / "cases" / "login-success.yaml",
        "kind: case\nid: auth.login.success\nname: login success\nmeta:\n  audit:\n    status: healthy\n    reasons: []\nspec:\n  apiRef: auth.post.login\n  request:\n    form:\n      username: guest\n      password: 123456\n  expect:\n    status: 200\n    assertions: []\n  extract: []\n",
    )

    project = load_project(tmp_path)
    document = {
        "openapi": "3.0.3",
        "paths": {
            "/login": {
                "post": {
                    "operationId": "login_post",
                    "summary": "Login",
                    "tags": ["AuthTag"],
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
            "/user": {
                "get": {
                    "operationId": "get_user",
                    "summary": "Get User",
                    "tags": ["AuthTag"],
                    "responses": {"200": {"description": "ok"}},
                }
            },
        },
    }

    normalized = normalize_openapi_document(project.sources["demo-openapi"], document)
    plan = plan_source_sync(project, "demo-openapi", normalized)
    report = apply_source_sync(project, "demo-openapi", plan)

    auth_root = apifox / "apis" / "auth"
    login_yaml, _ = _find_api_payload(auth_root, "auth.post.login")
    created_yaml, _ = _find_api_payload(auth_root, "auth.get.user")
    stale_yaml, _ = _find_api_payload(auth_root, "auth.get.stale")
    case_yaml = _read_yaml(apifox / "cases" / "login-success.yaml")

    assert login_yaml["meta"]["sync"]["lifecycle"] == "active"
    assert "tenantId" in login_yaml["spec"]["contract"]["request"]["formSchema"]
    assert created_yaml["meta"]["sync"]["lifecycle"] == "active"
    assert created_yaml["spec"]["contract"]["request"]["path"] == "/user"
    assert stale_yaml["meta"]["sync"]["lifecycle"] == "upstreamRemoved"
    assert case_yaml["spec"]["request"]["form"] == {"username": "guest", "password": 123456}

    report_files = sorted((apifox / "reports" / "sync").glob("*.yaml"))
    assert len(report_files) == 1
    report_yaml = _read_yaml(report_files[0])
    assert report_yaml["summary"]["createdApis"] == report.summary["createdApis"] == 1
    assert report_yaml["summary"]["updatedApis"] == report.summary["updatedApis"] == 1
    assert report_yaml["summary"]["upstreamRemovedApis"] == report.summary["upstreamRemovedApis"] == 1


def test_apply_source_sync_legacy_user_file_does_not_get_overwritten_by_get_post_user(tmp_path):
    apifox = tmp_path / "apifox"
    _create_base_project(apifox)
    _write_text(
        apifox / "apis" / "auth" / "user.yaml",
        "kind: api\nid: auth.legacy.user\nname: legacy user\nmeta:\n  module: auth\nspec:\n  protocol: http\n  contract:\n    request:\n      method: GET\n      path: /legacy-user\n    responses:\n      '200': {}\n",
    )

    project = load_project(tmp_path)
    document = {
        "openapi": "3.0.3",
        "paths": {
            "/user": {
                "get": {
                    "operationId": "get_user",
                    "summary": "Get User",
                    "tags": ["AuthTag"],
                    "responses": {"200": {"description": "ok"}},
                },
                "post": {
                    "operationId": "post_user",
                    "summary": "Create User",
                    "tags": ["AuthTag"],
                    "responses": {"200": {"description": "ok"}},
                },
            }
        },
    }

    normalized = normalize_openapi_document(project.sources["demo-openapi"], document)
    plan = plan_source_sync(project, "demo-openapi", normalized)
    apply_source_sync(project, "demo-openapi", plan)

    auth_root = apifox / "apis" / "auth"
    assert _read_yaml(auth_root / "user.yaml")["id"] == "auth.legacy.user"
    assert (auth_root / "get-user.yaml").exists()
    assert (auth_root / "post-user.yaml").exists()
    assert _read_yaml(auth_root / "get-user.yaml")["id"] == "auth.get.user"
    assert _read_yaml(auth_root / "post-user.yaml")["id"] == "auth.post.user"


def test_apply_source_sync_migrates_updated_api_to_new_path_and_removes_old_file(tmp_path):
    apifox = tmp_path / "apifox"
    _create_base_project(apifox)
    old_path = apifox / "apis" / "auth" / "post" / "login.yaml"
    _write_text(
        old_path,
        "kind: api\nid: auth.post.login\nname: login\nmeta:\n  module: auth\n  sync:\n    sourceId: demo-openapi\n    syncKey: login_post\n    lifecycle: active\nspec:\n  protocol: http\n  contract:\n    request:\n      method: POST\n      path: /login\n      contentType: application/x-www-form-urlencoded\n      formSchema:\n        username:\n          type: string\n          required: true\n        password:\n          type: string\n          required: true\n    responses:\n      '200': {}\n",
    )

    project = load_project(tmp_path)
    document = {
        "openapi": "3.0.3",
        "paths": {
            "/login": {
                "post": {
                    "operationId": "login_post",
                    "summary": "Login",
                    "tags": ["AuthTag"],
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
    apply_source_sync(project, "demo-openapi", plan)

    new_path = apifox / "apis" / "auth" / "post-login.yaml"
    assert new_path.exists()
    assert not old_path.exists()
    migrated = _read_yaml(new_path)
    assert migrated["id"] == "auth.post.login"
    assert "tenantId" in migrated["spec"]["contract"]["request"]["formSchema"]


def test_apply_source_sync_writes_unique_report_file_per_run(tmp_path):
    apifox = tmp_path / "apifox"
    _create_base_project(apifox)

    project = load_project(tmp_path)
    document = {
        "openapi": "3.0.3",
        "paths": {
            "/ping": {
                "get": {
                    "operationId": "ping_get",
                    "summary": "Ping",
                    "tags": ["AuthTag"],
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    }

    normalized = normalize_openapi_document(project.sources["demo-openapi"], document)
    plan = plan_source_sync(project, "demo-openapi", normalized)
    apply_source_sync(project, "demo-openapi", plan)
    apply_source_sync(project, "demo-openapi", plan)

    report_files = sorted((apifox / "reports" / "sync").glob("*.yaml"))
    assert len(report_files) == 2
    assert len({item.name for item in report_files}) == 2
