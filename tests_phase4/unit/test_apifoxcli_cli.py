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


def test_main_unknown_command_returns_non_zero():
    exit_code = main(["validate", "--project-root", "missing-project"])
    assert exit_code != 0
