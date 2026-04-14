import pytest
import yaml

from pytest_auto_api2.apifoxcli.loader import load_project
from pytest_auto_api2.apifoxcli.source_sync import (
    normalize_openapi_document,
    plan_source_sync,
)


def _write_yaml(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _build_source_payload(*, rebinds=None, tag_map=None):
    return {
        "kind": "source",
        "id": "demo-openapi",
        "name": "demo",
        "spec": {
            "type": "openapi",
            "url": "https://demo.example/openapi.json",
            "syncMode": "full",
            "includePaths": [],
            "excludePaths": [],
            "tagMap": tag_map or {"AuthTag": "auth"},
            "rebinds": rebinds or {},
            "guards": {"maxRemoveCount": 20, "maxRemoveRatio": 0.2},
        },
    }


def _build_api_payload(
    api_id,
    *,
    module,
    sync_key,
    method,
    path,
    required_fields=None,
    tags=None,
):
    form_schema = {
        field_name: {"type": "string", "required": True}
        for field_name in (required_fields or [])
    }
    request = {
        "method": method,
        "path": path,
        "contentType": "application/x-www-form-urlencoded" if form_schema else "application/json",
    }
    if form_schema:
        request["formSchema"] = form_schema
    return {
        "kind": "api",
        "id": api_id,
        "name": api_id.split(".")[-1],
        "meta": {
            "module": module,
            "tags": tags or ["AuthTag"],
            "sync": {
                "sourceId": "demo-openapi",
                "syncKey": sync_key,
                "upstreamMethod": method,
                "upstreamPath": path,
                "lifecycle": "active",
            },
        },
        "spec": {
            "protocol": "http",
            "contract": {"request": request, "responses": {"200": {}}},
        },
    }


def _load_project_with_source(tmp_path, *, source_payload, apis):
    apifox = tmp_path / "apifox"
    for rel in ("sources", "envs", "apis"):
        (apifox / rel).mkdir(parents=True, exist_ok=True)

    _write_yaml(
        apifox / "project.yaml",
        {"kind": "project", "id": "default", "name": "demo", "spec": {"defaultEnv": "qa"}},
    )
    _write_yaml(apifox / "sources" / "demo-openapi.yaml", source_payload)
    _write_yaml(
        apifox / "envs" / "qa.yaml",
        {
            "kind": "env",
            "id": "qa",
            "name": "QA",
            "spec": {
                "baseUrl": "https://demo.example/dev-api",
                "headers": {},
                "variables": {},
            },
        },
    )
    for payload in apis:
        rel_path = (apifox / "apis").joinpath(*payload["id"].split(".")).with_suffix(".yaml")
        _write_yaml(rel_path, payload)

    return load_project(tmp_path)


def test_plan_source_sync_detects_created_updated_and_removed_api(tmp_path):
    project = _load_project_with_source(
        tmp_path,
        source_payload=_build_source_payload(),
        apis=[
            _build_api_payload(
                "auth.login",
                module="auth",
                sync_key="login_post",
                method="POST",
                path="/login",
                required_fields=["username", "password"],
            ),
            _build_api_payload(
                "auth.removed",
                module="auth",
                sync_key="removed_get",
                method="GET",
                path="/removed",
            ),
        ],
    )
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
            "/getInfo": {
                "get": {
                    "operationId": "get_info_get",
                    "summary": "Get Info",
                    "tags": ["AuthTag"],
                    "responses": {"200": {"description": "ok"}},
                }
            },
        },
    }

    normalized = normalize_openapi_document(project.sources["demo-openapi"], document)
    plan = plan_source_sync(project, "demo-openapi", normalized)

    assert [item.api_id for item in plan.created] == ["auth.get.get-info"]
    assert [item.api_id for item in plan.updated] == ["auth.login"]
    assert [item.api_id for item in plan.upstream_removed] == ["auth.removed"]
    assert plan.updated[0].diffs[0].kind == "request.requiredAdded"
    assert plan.updated[0].diffs[0].field == "tenantId"


def test_normalize_openapi_document_distinguishes_methods_for_same_path(tmp_path):
    project = _load_project_with_source(
        tmp_path,
        source_payload=_build_source_payload(),
        apis=[],
    )
    document = {
        "openapi": "3.0.3",
        "paths": {
            "/session": {
                "get": {"tags": ["AuthTag"], "responses": {"200": {"description": "ok"}}},
                "post": {"tags": ["AuthTag"], "responses": {"200": {"description": "ok"}}},
            }
        },
    }

    normalized = normalize_openapi_document(project.sources["demo-openapi"], document)
    assert {item.api_id for item in normalized} == {"auth.get.session", "auth.post.session"}


def test_plan_source_sync_update_candidate_uses_upstream_module(tmp_path):
    project = _load_project_with_source(
        tmp_path,
        source_payload=_build_source_payload(tag_map={"AuthTag": "auth"}),
        apis=[
            _build_api_payload(
                "legacy.login",
                module="legacy",
                sync_key="login_post",
                method="POST",
                path="/login",
                required_fields=["username"],
            ),
        ],
    )
    document = {
        "openapi": "3.0.3",
        "paths": {
            "/login": {
                "post": {
                    "operationId": "login_post",
                    "tags": ["AuthTag"],
                    "requestBody": {
                        "content": {
                            "application/x-www-form-urlencoded": {
                                "schema": {
                                    "type": "object",
                                    "required": ["username", "tenantId"],
                                    "properties": {
                                        "username": {"type": "string"},
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

    assert [item.api_id for item in plan.updated] == ["legacy.login"]
    assert plan.updated[0].module == "auth"


def test_plan_source_sync_matches_operation_via_explicit_rebind_path(tmp_path):
    project = _load_project_with_source(
        tmp_path,
        source_payload=_build_source_payload(rebinds={"POST /signin": "auth.login"}),
        apis=[
            _build_api_payload(
                "auth.login",
                module="auth",
                sync_key="legacy_login_post",
                method="POST",
                path="/login",
            )
        ],
    )
    document = {
        "openapi": "3.0.3",
        "paths": {
            "/signin": {
                "post": {
                    "operationId": "signin_post",
                    "tags": ["AuthTag"],
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    }

    normalized = normalize_openapi_document(project.sources["demo-openapi"], document)
    plan = plan_source_sync(project, "demo-openapi", normalized)

    assert [item.api_id for item in plan.updated] == ["auth.login"]
    assert plan.created == []
    assert plan.upstream_removed == []


@pytest.mark.parametrize(
    ("apis", "message"),
    [
        (
            [
                _build_api_payload(
                    "auth.login.one",
                    module="auth",
                    sync_key="dup_login_post",
                    method="POST",
                    path="/login-one",
                ),
                _build_api_payload(
                    "auth.login.two",
                    module="auth",
                    sync_key="dup_login_post",
                    method="POST",
                    path="/login-two",
                ),
            ],
            "duplicate local sync key",
        ),
        (
            [
                _build_api_payload(
                    "auth.login.one",
                    module="auth",
                    sync_key="login_one_post",
                    method="POST",
                    path="/login",
                ),
                _build_api_payload(
                    "auth.login.two",
                    module="auth",
                    sync_key="login_two_post",
                    method="POST",
                    path="/login",
                ),
            ],
            r"duplicate local method\+path",
        ),
    ],
)
def test_plan_source_sync_fails_on_duplicate_local_bindings(tmp_path, apis, message):
    project = _load_project_with_source(
        tmp_path,
        source_payload=_build_source_payload(),
        apis=apis,
    )
    document = {
        "openapi": "3.0.3",
        "paths": {
            "/login": {
                "post": {
                    "operationId": "incoming_login_post",
                    "tags": ["AuthTag"],
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    }
    normalized = normalize_openapi_document(project.sources["demo-openapi"], document)

    with pytest.raises(ValueError, match=message):
        plan_source_sync(project, "demo-openapi", normalized)
