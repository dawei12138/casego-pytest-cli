from pytest_auto_api2.apifoxcli.context import RunContext
from pytest_auto_api2.apifoxcli.loader import load_project
from pytest_auto_api2.apifoxcli.planner import build_suite_plan
from pytest_auto_api2.apifoxcli.resolver import resolve_value


def test_resolve_value_uses_canonical_public_variable_syntax():
    context = RunContext(
        env={"baseUrl": "http://example.com", "variables": {"tenant": "qa"}},
        dataset={"username": "alice"},
    )
    context.values["token"] = "abc"
    payload = {
        "tenant": "${{tenant}}",
        "user": "${{username}}",
        "auth": "Bearer ${{token}}",
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
        "kind: api\nid: user.login\nname: login\nspec:\n  protocol: http\n  envRef: qa\n  request:\n    method: POST\n    path: /login\n    json:\n      username: ${{username}}\n  expect:\n    status: 200\n    assertions: []\n",
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


def test_build_suite_plan_expands_flow_steps_with_shared_context(tmp_path):
    apifox = tmp_path / "apifox"
    (apifox / "envs").mkdir(parents=True)
    (apifox / "apis").mkdir()
    (apifox / "flows").mkdir()
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
        "kind: api\nid: auth.login\nname: login\nspec:\n  protocol: http\n  envRef: qa\n  request:\n    method: POST\n    path: /login\n    form:\n      username: ${{username}}\n  expect:\n    status: 200\n    assertions: []\n  extract:\n    - name: token\n      from: response\n      expr: $.token\n",
        encoding="utf-8",
    )
    (apifox / "apis" / "profile.yaml").write_text(
        "kind: api\nid: auth.profile\nname: profile\nspec:\n  protocol: http\n  envRef: qa\n  request:\n    method: GET\n    path: /profile\n  expect:\n    status: 200\n    assertions: []\n",
        encoding="utf-8",
    )
    (apifox / "flows" / "bootstrap.yaml").write_text(
        "kind: flow\nid: auth.bootstrap\nname: bootstrap\nspec:\n  envRef: qa\n  steps:\n    - apiRef: auth.login\n    - apiRef: auth.profile\n",
        encoding="utf-8",
    )
    (apifox / "datasets" / "users.yaml").write_text(
        "kind: dataset\nid: auth.users\nname: users\nspec:\n  rows:\n    - username: alice\n    - username: bob\n",
        encoding="utf-8",
    )
    (apifox / "suites" / "smoke.yaml").write_text(
        "kind: suite\nid: smoke\nname: smoke\nspec:\n  envRef: qa\n  failFast: true\n  concurrency: 1\n  items:\n    - flowRef: auth.bootstrap\n      datasetRef: auth.users\n",
        encoding="utf-8",
    )

    project = load_project(tmp_path)
    plan = build_suite_plan(project, "smoke", env_override=None)

    assert [node.resource_id for node in plan.nodes] == [
        "auth.login",
        "auth.profile",
        "auth.login",
        "auth.profile",
    ]
    assert plan.nodes[0].dataset["username"] == "alice"
    assert plan.nodes[1].dataset["username"] == "alice"
    assert plan.nodes[2].dataset["username"] == "bob"
    assert plan.nodes[3].dataset["username"] == "bob"
    assert plan.nodes[0].context_key == plan.nodes[1].context_key
    assert plan.nodes[2].context_key == plan.nodes[3].context_key
    assert plan.nodes[0].context_key != plan.nodes[2].context_key
