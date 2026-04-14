import subprocess
import sys
from pathlib import Path

from pytest_auto_api2.apifoxcli import models


def test_import_models_has_no_pydantic_shadow_warning_and_keeps_json_alias():
    repo_root = Path(__file__).resolve().parents[2]
    script = """
from pytest_auto_api2.apifoxcli.models import RequestSpec

spec = RequestSpec(method='POST', path='/login', json={'username': 'alice'})
assert spec.json_body == {'username': 'alice'}
print('ok')
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "shadows an attribute in parent" not in result.stderr
    assert result.stdout.strip() == "ok"


def test_models_support_source_resource():
    source = models.SourceResource(
        kind="source",
        id="demo-openapi",
        name="demo",
        spec={
            "type": "openapi",
            "url": "https://demo.example/openapi.json",
            "syncMode": "full",
            "includePaths": [],
            "excludePaths": [],
            "tagMap": {},
            "guards": {"maxRemoveCount": 20, "maxRemoveRatio": 0.2},
        },
    )
    assert source.spec.type == "openapi"
    assert source.spec.guards.maxRemoveCount == 20


def test_models_support_case_resource_and_case_refs():
    case = models.CaseResource(
        kind="case",
        id="auth.login.success",
        name="login success",
        spec={
            "apiRef": "auth.login",
            "envRef": "qa",
            "request": {"form": {"username": "guest", "password": "123456"}},
            "expect": {"status": 200, "assertions": []},
            "extract": [],
        },
    )
    step = models.FlowStep(caseRef="auth.login.success")
    item = models.SuiteItem(caseRef="auth.login.success")

    assert case.spec.apiRef == "auth.login"
    assert step.caseRef == "auth.login.success"
    assert item.caseRef == "auth.login.success"
