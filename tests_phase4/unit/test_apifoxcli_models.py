import subprocess
import sys
from pathlib import Path


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
