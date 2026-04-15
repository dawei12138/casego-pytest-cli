from pytest_auto_api2.apifoxcli.cli import main
from pytest_auto_api2.apifoxcli.loader import load_project
from pytest_auto_api2.apifoxcli.validator import validate_project


def test_project_init_creates_sources_and_cases_layout(tmp_path):
    root = tmp_path / "demo"
    assert main(["project", "init", "--project-root", str(root), "--name", "demo-api"]) == 0
    assert (root / "apifox" / "sources").exists()
    assert (root / "apifox" / "cases").exists()


def test_loader_reads_source_case_and_case_refs(tmp_path):
    apifox = tmp_path / "apifox"
    for rel in ("sources", "envs", "apis", "cases", "flows", "suites"):
        (apifox / rel).mkdir(parents=True, exist_ok=True)

    (apifox / "project.yaml").write_text(
        "kind: project\nid: default\nname: demo\nspec:\n  defaultEnv: qa\n",
        encoding="utf-8",
    )
    (apifox / "sources" / "demo-openapi.yaml").write_text(
        "kind: source\nid: demo-openapi\nname: demo\nspec:\n  type: openapi\n  url: https://demo.example/openapi.json\n  syncMode: full\n  includePaths: []\n  excludePaths: []\n  tagMap: {}\n  guards:\n    maxRemoveCount: 20\n    maxRemoveRatio: 0.2\n",
        encoding="utf-8",
    )
    (apifox / "envs" / "qa.yaml").write_text(
        "kind: env\nid: qa\nname: QA\nspec:\n  baseUrl: https://demo.example/dev-api\n  headers: {}\n  variables: {}\n",
        encoding="utf-8",
    )
    (apifox / "apis" / "auth" / "login.yaml").parent.mkdir(parents=True, exist_ok=True)
    (apifox / "apis" / "auth" / "login.yaml").write_text(
        "kind: api\nid: auth.login\nname: login\nmeta:\n  module: auth\n  sync:\n    sourceId: demo-openapi\n    syncKey: login_post\n    lifecycle: active\nspec:\n  protocol: http\n  contract:\n    request:\n      method: POST\n      path: /login\n      contentType: application/x-www-form-urlencoded\n      formSchema:\n        username:\n          type: string\n          required: true\n        password:\n          type: string\n          required: true\n    responses:\n      '200': {}\n",
        encoding="utf-8",
    )
    (apifox / "cases" / "auth" / "login-success.yaml").parent.mkdir(parents=True, exist_ok=True)
    (apifox / "cases" / "auth" / "login-success.yaml").write_text(
        "kind: case\nid: auth.login.success\nname: login success\nspec:\n  apiRef: auth.login\n  envRef: qa\n  request:\n    form:\n      username: guest\n      password: 123456\n  expect:\n    status: 200\n    assertions: []\n  extract: []\n",
        encoding="utf-8",
    )
    (apifox / "flows" / "auth-bootstrap.yaml").write_text(
        "kind: flow\nid: auth.bootstrap\nname: auth bootstrap\nspec:\n  envRef: qa\n  steps:\n    - caseRef: auth.login.success\n",
        encoding="utf-8",
    )
    (apifox / "suites" / "smoke.yaml").write_text(
        "kind: suite\nid: smoke\nname: smoke\nspec:\n  envRef: qa\n  failFast: true\n  concurrency: 1\n  items:\n    - caseRef: auth.login.success\n    - flowRef: auth.bootstrap\n",
        encoding="utf-8",
    )

    project = load_project(tmp_path)
    assert "demo-openapi" in project.sources
    assert "auth.login.success" in project.cases
    assert project.flows["auth.bootstrap"].spec.steps[0].caseRef == "auth.login.success"
    assert project.suites["smoke"].spec.items[0].caseRef == "auth.login.success"


def test_validator_rejects_missing_case_reference(tmp_path):
    apifox = tmp_path / "apifox"
    for rel in ("envs", "flows", "suites"):
        (apifox / rel).mkdir(parents=True, exist_ok=True)

    (apifox / "project.yaml").write_text(
        "kind: project\nid: default\nname: demo\nspec:\n  defaultEnv: qa\n",
        encoding="utf-8",
    )
    (apifox / "envs" / "qa.yaml").write_text(
        "kind: env\nid: qa\nname: QA\nspec:\n  baseUrl: http://example.com\n  headers: {}\n  variables: {}\n",
        encoding="utf-8",
    )
    (apifox / "flows" / "broken.yaml").write_text(
        "kind: flow\nid: broken\nname: broken\nspec:\n  steps:\n    - caseRef: missing.case\n",
        encoding="utf-8",
    )

    project = load_project(tmp_path)
    errors = validate_project(project)
    assert any("caseRef not found" in item for item in errors)
