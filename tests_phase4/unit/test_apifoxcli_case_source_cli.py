import json

from pytest_auto_api2.apifoxcli.cli import build_parser, main
from pytest_auto_api2.apifoxcli.loader import load_project


def _write_source(root, source_id="demo-openapi", source_url="https://demo.example/openapi.json"):
    source_path = root / "apifox" / "sources" / f"{source_id}.yaml"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text(
        f"""kind: source
id: {source_id}
name: {source_id}
spec:
  type: openapi
  url: {source_url}
  syncMode: full
  includePaths: []
  excludePaths: []
  tagMap: {{}}
  rebinds: {{}}
  guards:
    maxRemoveCount: 20
    maxRemoveRatio: 0.2
""",
        encoding="utf-8",
    )


def test_build_parser_supports_case_and_source_commands():
    parser = build_parser()
    case_args = parser.parse_args(["case", "run", "auth.login.success", "--env", "qa", "--dataset", "auth.users"])
    sync_args = parser.parse_args(["source", "sync", "demo-openapi", "--apply"])
    status_args = parser.parse_args(["source", "status", "demo-openapi"])
    rebind_args = parser.parse_args(["source", "rebind", "demo-openapi", "--api-id", "auth.post.login", "--sync-key", "login_post"])

    assert case_args.resource == "case"
    assert case_args.action == "run"
    assert sync_args.resource == "source"
    assert sync_args.action == "sync"
    assert sync_args.apply is True
    assert status_args.action == "status"
    assert rebind_args.action == "rebind"


def test_source_rebind_persists_source_spec_rebinds(tmp_path):
    root = tmp_path / "demo"
    assert main(["project", "init", "--project-root", str(root)]) == 0
    _write_source(root)

    exit_code = main(
        [
            "source",
            "rebind",
            "demo-openapi",
            "--project-root",
            str(root),
            "--api-id",
            "auth.post.login",
            "--sync-key",
            "login_post",
        ]
    )

    project = load_project(root)
    assert exit_code == 0
    assert project.sources["demo-openapi"].spec.rebinds["login_post"] == "auth.post.login"


def test_source_status_returns_non_zero_with_clear_error_when_report_missing(tmp_path, capsys):
    root = tmp_path / "demo"
    assert main(["project", "init", "--project-root", str(root)]) == 0
    _write_source(root)

    exit_code = main(["source", "status", "demo-openapi", "--project-root", str(root)])
    stderr = capsys.readouterr().err

    assert exit_code != 0
    assert "no sync report found for source 'demo-openapi'" in stderr


def test_source_sync_failure_surfaces_exception_text(tmp_path, capsys):
    root = tmp_path / "demo"
    assert main(["project", "init", "--project-root", str(root)]) == 0
    _write_source(root, source_url=str(tmp_path / "missing-openapi.json"))

    exit_code = main(["source", "sync", "demo-openapi", "--project-root", str(root)])
    stderr = capsys.readouterr().err

    assert exit_code != 0
    assert "No such file or directory" in stderr


def test_source_status_failure_with_json_emits_structured_error(tmp_path, capsys):
    root = tmp_path / "demo"
    assert main(["project", "init", "--project-root", str(root)]) == 0
    _write_source(root)

    exit_code = main(["source", "status", "demo-openapi", "--project-root", str(root), "--json"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out.strip())

    assert exit_code != 0
    assert payload["error"]["type"] == "FileNotFoundError"
    assert "no sync report found" in payload["error"]["message"]
    assert captured.err == ""
