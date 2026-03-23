# AI Skill Readiness Progress

Last updated: 2026-03-23 (A1/A2/A3/A4/A5 completed)

| Stage | Task ID | Task | Status | Notes |
| --- | --- | --- | --- | --- |
| Stage A | A1 | Remove dynamic execution (`eval`/`exec`) from generation/execution path | Completed | Removed `exec` from `dependent_case.py` + `teardown_control.py`; replaced generator `eval` with `ast.literal_eval` |
| Stage A | A2 | Add `api2 validate` command for YAML/schema/dependency pre-check | Completed | Added `api2 validate` + `--json`, with duplicate `case_id`/schema-style pre-checks and non-zero exit on validation failures |
| Stage A | A3 | Add `api2 run --json` structured result output for AI orchestration | Completed | Added pytest summary/failure collection and machine-readable JSON payload (`summary`, `failed_cases`, `error_cases`, `exit_code`) |
| Stage A | A4 | Regeneration stability for historical broken `test_case` files | Completed | Added safe decorator string rendering in template and `api2 gen --force` / `api2 all --force-gen` to support forced overwrite even when `real_time_update_test_cases` is false |
| Stage A | A5 | Stabilize `test_case/conftest.py` summary output | Completed | Rebuilt `pytest_terminal_summary` to use terminal output instead of logger handlers; removed closed-stream noise during pytest teardown |
| Stage B | B1 | Secrets hygiene (`config.template.yaml`, env substitution) | Pending | Remove default real webhook/password values |
| Stage B | B2 | Side-effect control for login/bootstrap fixtures | Pending | Make login bootstrap opt-in |
| Stage B | B3 | Cache isolation per run (run_id namespace) | Pending | Avoid cross-task cache contamination |
| Stage B | B4 | Exit code contract and error taxonomy | Pending | Stable machine contract for skills |

## Verification (2026-03-23)

- `venv\Scripts\python.exe -m py_compile pytest_auto_api2/cli.py utils/requests_tool/dependent_case.py utils/requests_tool/teardown_control.py utils/read_files_tools/testcase_template.py tests_phase3/unit/test_cli_unit.py tests_phase3/integration/test_cli_integration.py` -> pass
- `venv\Scripts\python.exe -m pytest -q tests_phase3` -> `10 passed`
- `venv\Scripts\python.exe -m pytest_auto_api2.cli validate --project-root . --json` -> `ok: true`, `error_count: 0`
- `venv\Scripts\python.exe -m pytest_auto_api2.cli run --project-root . --json tests_phase3/unit/test_cli_unit.py` -> `exit_code: 0`, `passed: 4`
- `venv\Scripts\python.exe -m pytest_auto_api2.cli gen --project-root . --force` -> regenerated broken `test_case/*` files without changing global config
- `venv\Scripts\python.exe -m py_compile test_case/conftest.py test_case/Collect/test_collect_addtool.py test_case/Collect/test_collect_delete_tool.py test_case/Collect/test_collect_tool_list.py test_case/Collect/test_collect_update_tool.py test_case/Login/test_login.py test_case/UserInfo/test_get_user_info.py` -> pass
- `venv\Scripts\python.exe -m pytest_auto_api2.cli run --project-root . --json` -> enters execution stage and returns structured errors (network-restricted env), no syntax-collection blocker

## Known Gaps For Next Stage

- `work_login_init` in `test_case/conftest.py` still performs real external login in session setup; network-restricted or offline environments will fail before business assertions.
- `common/config.yaml` still contains real webhook/token/password-style values and should be converted to template/env substitution for skills-safe distribution.
