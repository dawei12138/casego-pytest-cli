from pytest_auto_api2.apifoxcli.context import RunContext
from pytest_auto_api2.apifoxcli.loader import load_project
from pytest_auto_api2.apifoxcli.planner import build_suite_plan
from pytest_auto_api2.apifoxcli.resolver import resolve_value


def test_resolve_value_uses_env_context_and_dataset():
    context = RunContext(
        env={"baseUrl": "http://example.com", "variables": {"tenant": "qa"}},
        dataset={"username": "alice"},
    )
    context.values["token"] = "abc"
    payload = {
        "tenant": "${env.tenant}",
        "user": "${dataset.username}",
        "auth": "Bearer ${context.token}",
    }
    assert resolve_value(payload, context) == {
        "tenant": "qa",
        "user": "alice",
        "auth": "Bearer abc",
    }


def test_build_suite_plan_expands_dataset_rows(tmp_path):
    apifox = tmp_path / "apifox"
    (apifox / "envs").mkdir(parents=True)
    (apifox / "apis").mkdir()
    (apifox / "suites").mkdir()
    (apifox / "datasets").mkdir()
    (apifox / "project.yaml").write_text(
        "kind: project\nid: default\nname: demo\nspec:\n  defaultEnv: qa\n",
        encoding="utf-8",
    )
    (apifox / "envs" / "qa.yaml").write_text(
        "kind: env\nid: qa\nname: qa\nspec:\n  baseUrl: http://example.com\n  variables: {}\n",
        encoding="utf-8",
    )
    (apifox / "apis" / "login.yaml").write_text(
        "kind: api\nid: user.login\nname: login\nspec:\n  protocol: http\n  envRef: qa\n  request:\n    method: POST\n    path: /login\n    json:\n      username: ${dataset.username}\n  expect:\n    status: 200\n    assertions: []\n",
        encoding="utf-8",
    )
    (apifox / "datasets" / "users.yaml").write_text(
        "kind: dataset\nid: user.rows\nname: users\nspec:\n  rows:\n    - username: alice\n    - username: bob\n",
        encoding="utf-8",
    )
    (apifox / "suites" / "smoke.yaml").write_text(
        "kind: suite\nid: smoke\nname: smoke\nspec:\n  envRef: qa\n  failFast: true\n  concurrency: 1\n  items:\n    - apiRef: user.login\n      datasetRef: user.rows\n",
        encoding="utf-8",
    )

    project = load_project(tmp_path)
    plan = build_suite_plan(project, "smoke", env_override=None)
    assert len(plan.nodes) == 2
    assert plan.nodes[0].dataset["username"] == "alice"
    assert plan.nodes[1].dataset["username"] == "bob"
