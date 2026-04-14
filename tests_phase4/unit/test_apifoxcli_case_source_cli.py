import json

import pytest

from pytest_auto_api2.apifoxcli.cli import build_parser, main
from pytest_auto_api2.apifoxcli.loader import load_project


def _write_source(
    root,
    source_id="demo-openapi",
    source_url="https://demo.example/openapi.json",
    *,
    max_remove_count=20,
    max_remove_ratio=0.2,
):
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
    maxRemoveCount: {max_remove_count}
    maxRemoveRatio: {max_remove_ratio}
""",
        encoding="utf-8",
    )


def _write_synced_api(root, api_id="auth.get.stale", sync_key="stale_get", path="/stale"):
    api_path = root / "apifox" / "apis" / "auth" / "stale.yaml"
    api_path.parent.mkdir(parents=True, exist_ok=True)
    api_path.write_text(
        f"""kind: api
id: {api_id}
name: stale
meta:
  module: auth
  sync:
    sourceId: demo-openapi
    syncKey: {sync_key}
    lifecycle: active
spec:
  protocol: http
  contract:
    request:
      method: GET
      path: {path}
      contentType: application/json
    responses:
      '200': {{}}
""",
        encoding="utf-8",
    )
    return api_path


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


def test_build_parser_rejects_source_sync_apply_and_plan_together():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["source", "sync", "demo-openapi", "--apply", "--plan"])


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


def test_source_sync_default_mode_is_plan_only_without_report_write(tmp_path):
    root = tmp_path / "demo"
    assert main(["project", "init", "--project-root", str(root)]) == 0
    source_path = tmp_path / "openapi.json"
    source_path.write_text(
        json.dumps(
            {
                "openapi": "3.0.3",
                "paths": {
                    "/ping": {
                        "get": {
                            "operationId": "ping_get",
                            "tags": ["PingTag"],
                            "responses": {"200": {"description": "ok"}},
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    _write_source(root, source_url=str(source_path))

    exit_code = main(["source", "sync", "demo-openapi", "--project-root", str(root)])

    report_dir = root / "apifox" / "reports" / "sync"
    assert exit_code == 0
    assert not report_dir.exists() or list(report_dir.glob("*.yaml")) == []


def test_source_sync_plan_flag_is_plan_only_without_report_write(tmp_path):
    root = tmp_path / "demo"
    assert main(["project", "init", "--project-root", str(root)]) == 0
    source_path = tmp_path / "openapi.json"
    source_path.write_text(
        json.dumps(
            {
                "openapi": "3.0.3",
                "paths": {
                    "/ping": {
                        "get": {
                            "operationId": "ping_get",
                            "tags": ["PingTag"],
                            "responses": {"200": {"description": "ok"}},
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    _write_source(root, source_url=str(source_path))

    exit_code = main(["source", "sync", "demo-openapi", "--project-root", str(root), "--plan"])

    report_dir = root / "apifox" / "reports" / "sync"
    assert exit_code == 0
    assert not report_dir.exists() or list(report_dir.glob("*.yaml")) == []


def test_source_sync_prune_requires_apply(tmp_path, capsys):
    root = tmp_path / "demo"
    assert main(["project", "init", "--project-root", str(root)]) == 0
    source_path = tmp_path / "openapi.json"
    source_path.write_text(
        json.dumps({"openapi": "3.0.3", "paths": {}}),
        encoding="utf-8",
    )
    _write_source(root, source_url=str(source_path))

    exit_code = main(["source", "sync", "demo-openapi", "--project-root", str(root), "--prune"])
    stderr = capsys.readouterr().err

    assert exit_code != 0
    assert "--prune requires --apply" in stderr


def test_source_sync_apply_prune_removes_unreferenced_upstream_removed_api(tmp_path):
    root = tmp_path / "demo"
    assert main(["project", "init", "--project-root", str(root)]) == 0
    source_path = tmp_path / "openapi.json"
    source_path.write_text(json.dumps({"openapi": "3.0.3", "paths": {}}), encoding="utf-8")
    _write_source(root, source_url=str(source_path), max_remove_count=20, max_remove_ratio=1.0)
    stale_path = _write_synced_api(root)

    exit_code = main(
        ["source", "sync", "demo-openapi", "--project-root", str(root), "--apply", "--prune"]
    )

    project = load_project(root)
    assert exit_code == 0
    assert not stale_path.exists()
    assert "auth.get.stale" not in project.apis


def test_source_sync_apply_prune_fails_when_prune_guards_block(tmp_path, capsys):
    root = tmp_path / "demo"
    assert main(["project", "init", "--project-root", str(root)]) == 0
    source_path = tmp_path / "openapi.json"
    source_path.write_text(json.dumps({"openapi": "3.0.3", "paths": {}}), encoding="utf-8")
    _write_source(root, source_url=str(source_path), max_remove_count=0, max_remove_ratio=0.0)
    _write_synced_api(root)

    exit_code = main(
        ["source", "sync", "demo-openapi", "--project-root", str(root), "--apply", "--prune"]
    )
    stderr = capsys.readouterr().err

    assert exit_code != 0
    assert "prune guard exceeded" in stderr


def test_project_import_openapi_loads_document_once(tmp_path, monkeypatch):
    from pytest_auto_api2.apifoxcli import cli as cli_module

    root = tmp_path / "demo"
    assert cli_module.main(["project", "init", "--project-root", str(root)]) == 0
    source_path = tmp_path / "openapi.json"
    source_path.write_text(
        json.dumps(
            {
                "openapi": "3.0.3",
                "servers": [{"url": "https://demo.example/dev-api", "description": "qa"}],
                "paths": {
                    "/ping": {
                        "get": {
                            "operationId": "ping_get",
                            "responses": {"200": {"description": "ok"}},
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    calls = []
    real_loader = cli_module.load_openapi_document

    def _tracked_loader(source, *, root=None):
        calls.append((source, root))
        return real_loader(source, root=root)

    monkeypatch.setattr(cli_module, "load_openapi_document", _tracked_loader)

    exit_code = cli_module.main(
        [
            "project",
            "import-openapi",
            "--project-root",
            str(root),
            "--source",
            str(source_path),
            "--source-id",
            "demo-openapi",
            "--server-description",
            "qa",
        ]
    )
    assert exit_code == 0
    assert len(calls) == 1
