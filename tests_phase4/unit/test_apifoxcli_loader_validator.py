from pytest_auto_api2.apifoxcli.cli import main
from pytest_auto_api2.apifoxcli.loader import load_project
from pytest_auto_api2.apifoxcli.validator import validate_project


def test_project_init_creates_canonical_layout(tmp_path):
    root = tmp_path / "demo"
    exit_code = main(["project", "init", "--project-root", str(root)])
    assert exit_code == 0
    assert (root / "apifox" / "project.yaml").exists()
    assert (root / "apifox" / "envs" / "qa.yaml").exists()
    assert (root / "apifox" / "suites" / "smoke.yaml").exists()


def test_loader_reads_canonical_resources(tmp_path):
    apifox = tmp_path / "apifox"
    (apifox / "envs").mkdir(parents=True)
    (apifox / "apis").mkdir()
    (apifox / "project.yaml").write_text(
        "kind: project\nid: default\nname: demo\nspec:\n  defaultEnv: qa\n",
        encoding="utf-8",
    )
    (apifox / "envs" / "qa.yaml").write_text(
        "kind: env\nid: qa\nname: qa\nspec:\n  baseUrl: http://example.com\n  variables: {}\n",
        encoding="utf-8",
    )
    (apifox / "apis" / "login.yaml").write_text(
        "kind: api\nid: user.login\nname: login\nspec:\n  protocol: http\n  envRef: qa\n  request:\n    method: POST\n    path: /user/login\n    json: {}\n  expect:\n    status: 200\n    assertions: []\n",
        encoding="utf-8",
    )

    project = load_project(tmp_path)
    assert project.project.id == "default"
    assert "qa" in project.envs
    assert "user.login" in project.apis


def test_validator_rejects_missing_env_reference(tmp_path):
    apifox = tmp_path / "apifox"
    (apifox / "apis").mkdir(parents=True)
    (apifox / "project.yaml").write_text(
        "kind: project\nid: default\nname: demo\nspec:\n  defaultEnv: qa\n",
        encoding="utf-8",
    )
    (apifox / "apis" / "login.yaml").write_text(
        "kind: api\nid: user.login\nname: login\nspec:\n  protocol: http\n  envRef: qa\n  request:\n    method: POST\n    path: /user/login\n    json: {}\n  expect:\n    status: 200\n    assertions: []\n",
        encoding="utf-8",
    )

    project = load_project(tmp_path)
    errors = validate_project(project)
    assert any("envRef" in item for item in errors)
