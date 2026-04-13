from pytest_auto_api2.apifoxcli.cli import build_parser, main


def test_build_parser_supports_project_init():
    parser = build_parser()
    args = parser.parse_args(["project", "init", "--project-root", "demo"])
    assert args.resource == "project"
    assert args.action == "init"
    assert args.project_root == "demo"


def test_build_parser_supports_api_send():
    parser = build_parser()
    args = parser.parse_args(["api", "send", "user.login", "--env", "qa", "--json"])
    assert args.resource == "api"
    assert args.action == "send"
    assert args.resource_id == "user.login"
    assert args.env == "qa"
    assert args.json is True


def test_build_parser_supports_flow_run():
    parser = build_parser()
    args = parser.parse_args(
        ["flow", "run", "auth.bootstrap", "--env", "qa", "--dataset", "auth.users", "--json"]
    )
    assert args.resource == "flow"
    assert args.action == "run"
    assert args.resource_id == "auth.bootstrap"
    assert args.env == "qa"
    assert args.dataset == "auth.users"
    assert args.json is True


def test_build_parser_supports_project_import_openapi():
    parser = build_parser()
    args = parser.parse_args(
        [
            "project",
            "import-openapi",
            "--project-root",
            "demo",
            "--source",
            "https://example.com/openapi.json",
            "--server-description",
            "qa",
            "--include-path",
            "/login",
            "--include-path",
            "/getInfo",
        ]
    )
    assert args.resource == "project"
    assert args.action == "import-openapi"
    assert args.project_root == "demo"
    assert args.source == "https://example.com/openapi.json"
    assert args.server_description == "qa"
    assert args.include_path == ["/login", "/getInfo"]


def test_main_unknown_command_returns_non_zero():
    exit_code = main(["validate", "--project-root", "missing-project"])
    assert exit_code != 0


def test_validate_returns_exit_code_2_for_unsupported_expression(tmp_path):
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
    (apifox / "apis" / "broken.yaml").write_text(
        "kind: api\nid: broken.api\nname: broken\nspec:\n  protocol: http\n  envRef: qa\n  request:\n    method: GET\n    path: /broken\n    headers:\n      Authorization: ${bad.token}\n  expect:\n    status: 200\n    assertions: []\n",
        encoding="utf-8",
    )

    exit_code = main(["validate", "--project-root", str(tmp_path)])
    assert exit_code == 2
