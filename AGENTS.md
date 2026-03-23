# Repository Guidelines

## Project Structure & Module Organization
- `common/`: global settings (`config.yaml`, `setting.py`).
- `data/`: YAML source cases grouped by feature (for example `data/Collect/collect_tool_list.yaml`).
- `test_case/`: generated/executable pytest modules mirroring `data/` (for example `test_case/Collect/test_collect_tool_list.py`).
- `utils/`: framework internals (request engine, assertions, code generation, notifications, logging).
- `Files/`: upload fixtures and README images.
- Runtime outputs: `logs/`, `report/` (created during runs), and `.coverage`.

## Build, Test, and Development Commands
Prerequisites: Python 3.x, JDK, and Allure CLI.
- `pip3 install -r requirements.txt`: install project dependencies.
- `python utils/read_files_tools/case_automatic_control.py`: regenerate pytest files from YAML after editing `data/`.
- `pytest -s`: run tests with repository discovery rules.
- `pytest -m smoke -s`: run smoke tests only.
- `python run.py`: main entrypoint; runs pytest, builds Allure data, and dispatches notifications.
- `allure generate ./report/tmp -o ./report/html --clean`: build a static Allure report.
- `allure serve ./report/tmp -h 127.0.0.1 -p 9999`: launch local interactive report.

## Coding Style & Naming Conventions
- Use 4-space indentation and UTF-8 encoding in Python files.
- Follow existing pytest naming from `pytest.ini`:
  - files: `test_*.py`
  - classes: `Test*`
  - functions: `test_*`
- Keep `data/<feature>/xxx.yaml` and `test_case/<feature>/test_xxx.py` aligned.
- Prefer adding shared logic in `utils/` instead of duplicating request/assert code in test modules.

## Testing Guidelines
- `pytest.ini` sets discovery under `test_case/` and defines marker `smoke`.
- Change YAML in `data/` first, then regenerate corresponding tests.
- For endpoint updates, include normal-path checks and at least one explicit assertion (`status_code` or JSONPath assertion data).
- For order-dependent flows, verify collection-order behavior in `test_case/conftest.py`.

## Commit & Pull Request Guidelines
- Recent history uses short, scoped messages with prefixes like `fix`, `新增`, and `优化`.
- Keep each commit single-purpose; mention regenerated files when YAML changes produce new test code.
- PRs should include: scope, config impact (`common/config.yaml`), commands executed, and a concise result summary (plus report screenshots when output changes).

## Security & Configuration Tips
- `common/config.yaml` includes webhook/email/database settings and can hold sensitive values.
- Do not commit real tokens, secrets, or private endpoints; sanitize configuration before pushing.
