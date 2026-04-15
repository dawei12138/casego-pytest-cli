from pytest_auto_api2.apifoxcli.context import RunContext
from pytest_auto_api2.apifoxcli.loader import load_project
from pytest_auto_api2.apifoxcli.resolver import resolve_value
from pytest_auto_api2.apifoxcli.validator import validate_project


def test_resolve_value_uses_public_double_brace_syntax_with_runtime_precedence():
    context = RunContext(
        env={"variables": {"token": "env-token", "username": "guest"}},
        dataset={"username": "row-user"},
        values={"token": "runtime-token"},
    )

    assert resolve_value("Bearer ${{token}}", context) == "Bearer runtime-token"
    assert resolve_value("${{username}}", context) == "row-user"


def test_validate_project_accepts_public_double_brace_syntax(tmp_path):
    apifox = tmp_path / "apifox"
    (apifox / "envs").mkdir(parents=True)
    (apifox / "apis").mkdir()
    (apifox / "cases").mkdir()
    (apifox / "project.yaml").write_text(
        "kind: project\nid: default\nname: demo\nspec:\n  defaultEnv: qa\n",
        encoding="utf-8",
    )
    (apifox / "envs" / "qa.yaml").write_text(
        "kind: env\nid: qa\nname: qa\nspec:\n  baseUrl: http://example.com\n  headers:\n    Authorization: Bearer ${{token}}\n  variables:\n    token: env-token\n",
        encoding="utf-8",
    )
    (apifox / "apis" / "login.yaml").write_text(
        "kind: api\nid: auth.login\nname: login\nspec:\n  protocol: http\n  envRef: qa\n  contract:\n    request:\n      method: POST\n      path: /users/{userId}\n    responses:\n      '200': {}\n  request:\n    method: POST\n    path: /users/${{userId}}\n    json:\n      username: ${{username}}\n  expect:\n    status: 200\n    assertions: []\n",
        encoding="utf-8",
    )
    (apifox / "cases" / "login.yaml").write_text(
        "kind: case\nid: auth.login.case\nname: login case\nspec:\n  apiRef: auth.login\n  envRef: qa\n  request:\n    json:\n      username: ${{username}}\n  expect:\n    status: 200\n    assertions: []\n  extract: []\n",
        encoding="utf-8",
    )

    project = load_project(tmp_path)
    assert validate_project(project) == []


def test_validate_project_rejects_legacy_public_dotted_syntax(tmp_path):
    apifox = tmp_path / "apifox"
    (apifox / "envs").mkdir(parents=True)
    (apifox / "apis").mkdir()
    (apifox / "cases").mkdir()
    (apifox / "project.yaml").write_text(
        "kind: project\nid: default\nname: demo\nspec:\n  defaultEnv: qa\n",
        encoding="utf-8",
    )
    (apifox / "envs" / "qa.yaml").write_text(
        "kind: env\nid: qa\nname: qa\nspec:\n  baseUrl: http://example.com\n  headers:\n    Authorization: Bearer ${context.token}\n  variables: {}\n",
        encoding="utf-8",
    )
    (apifox / "apis" / "login.yaml").write_text(
        "kind: api\nid: auth.login\nname: login\nspec:\n  protocol: http\n  envRef: qa\n  contract:\n    request:\n      method: POST\n      path: /orders/${context.orderId}\n    responses:\n      '200': {}\n  request:\n    method: POST\n    path: /users/${dataset.userId}\n    json:\n      username: ${dataset.username}\n  expect:\n    status: 200\n    assertions: []\n",
        encoding="utf-8",
    )
    (apifox / "cases" / "login.yaml").write_text(
        "kind: case\nid: auth.login.case\nname: login case\nspec:\n  apiRef: auth.login\n  envRef: qa\n  request:\n    headers:\n      X-Tenant: ${env.tenant}\n  expect:\n    status: 200\n    assertions: []\n  extract: []\n",
        encoding="utf-8",
    )

    project = load_project(tmp_path)
    errors = validate_project(project)

    assert any("context.token" in item for item in errors)
    assert any("context.orderId" in item for item in errors)
    assert any("dataset.userId" in item for item in errors)
    assert any("dataset.username" in item for item in errors)
    assert any("env.tenant" in item for item in errors)


def test_validate_project_rejects_raw_public_request_path_template(tmp_path):
    apifox = tmp_path / "apifox"
    (apifox / "envs").mkdir(parents=True)
    (apifox / "apis").mkdir()
    (apifox / "project.yaml").write_text(
        "kind: project\nid: default\nname: demo\nspec:\n  defaultEnv: qa\n",
        encoding="utf-8",
    )
    (apifox / "envs" / "qa.yaml").write_text(
        "kind: env\nid: qa\nname: qa\nspec:\n  baseUrl: http://example.com\n  headers: {}\n  variables: {}\n",
        encoding="utf-8",
    )
    (apifox / "apis" / "detail.yaml").write_text(
        "kind: api\nid: auth.detail\nname: detail\nspec:\n  protocol: http\n  envRef: qa\n  contract:\n    request:\n      method: GET\n      path: /users/{userId}\n    responses:\n      '200': {}\n  request:\n    method: GET\n    path: /users/{userId}\n  expect:\n    status: 200\n    assertions: []\n",
        encoding="utf-8",
    )

    project = load_project(tmp_path)
    errors = validate_project(project)

    assert any("raw path template" in item for item in errors)
    assert any("auth.detail" in item for item in errors)
