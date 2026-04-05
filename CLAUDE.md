# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

pytest-auto-api2 is a data-driven API automated testing framework (Python + pytest + Allure). Test cases are defined in YAML files under `data/`, auto-generated into Python test code under `test_case/`, and executed via pytest. The framework supports multi-interface dependencies, database assertions, dynamic value replacement, and multi-channel notifications (DingTalk, WeChat, Email, Lark).

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Install as CLI tool (provides `casego` command)
pip install -e .

# Initialize a new project scaffold in current directory
casego init

# Validate YAML test definitions (check structure, duplicates)
casego validate
casego validate --json          # machine-readable output

# Auto-generate Python test code from YAML definitions
casego gen
casego gen --force              # force overwrite existing test files

# Run tests
casego run                      # run all tests
casego run -m smoke             # run only smoke-marked tests
casego run -k test_login        # run by keyword
casego run --json               # machine-readable JSON result
casego run --allure --generate-report  # with Allure report

# Generate + run in one step
casego all --allure --generate-report --serve-report

# Legacy entrypoint (runs pytest + Allure + notifications)
python run.py

# Direct pytest
pytest -s test_case/
pytest -s test_case/ -m smoke
```

### Environment Variables

Paths can be overridden via env vars:
- `PYTEST_AUTO_API2_HOME` — project root
- `PYTEST_AUTO_API2_CONFIG` — config file path
- `PYTEST_AUTO_API2_DATA_DIR` — YAML data directory
- `PYTEST_AUTO_API2_TEST_DIR` — generated test directory

## Architecture

### Dual Directory Structure

The project has two layers:
- **`pytest_auto_api2/`** — the installable package (CLI, runtime loader, utils, common settings). This is what `casego` uses and what `pyproject.toml` packages.
- **Root-level `common/`, `data/`, `test_case/`, `utils/`** — the working project instance. `test_case/conftest.py` and generated tests import from `pytest_auto_api2.*`.

Both `utils/` and `pytest_auto_api2/utils/` exist; the package version is canonical. Root `common/setting.py` and `pytest_auto_api2/common/setting.py` share the same path-resolution logic.

### Execution Flow

1. YAML test cases in `data/` are parsed and loaded into a case pool via `pytest_auto_api2/runtime/loader.py` (called from `test_case/__init__.py`)
2. Python test files in `test_case/` are auto-generated from YAML via `casego gen` (uses `case_automatic_control.py`)
3. Session fixtures in `test_case/conftest.py` handle login/auth and test ordering
4. Each test: resolve dependencies → execute HTTP request → run assertions → teardown cleanup
5. `run.py` or `casego all` orchestrates: pytest execution → Allure report → notifications

### Key Modules (under `pytest_auto_api2/utils/`)

- **`requests_tool/request_control.py`** — `RequestControl`: HTTP request wrapper (GET/POST/PUT/DELETE/PATCH), handles content types (JSON, form-data, multipart, file upload)
- **`requests_tool/dependent_case.py`** — `DependentCase`: resolves multi-level case dependencies using JSONPath extraction
- **`assertion/assert_control.py`** — `AssertUtil`: response assertions (JSONPath-based), database assertions, operators: `==`, `!=`, `<`, `>`, `in`, `not_in`, regex
- **`read_files_tools/regular_control.py`** — Dynamic value replacement: `${{func_name()}}` for functions, `$cache{name}` for cache references
- **`read_files_tools/get_yaml_data_analysis.py`** — Parses and validates YAML test case structure into Pydantic models
- **`other_tools/models.py`** — Pydantic data models (`TestCase`, `DependentData`, `ResponseData`, etc.) and enums (`RequestType`, `Method`, `DependentType`)
- **`cache_process/cache_control.py`** — In-memory dict-based cache for sharing data between test cases
- **`requests_tool/teardown_control.py`** — Post-test cleanup via API calls or SQL execution

### YAML Test Case Structure

Each YAML file in `data/` contains `case_common` (Allure metadata) and individual cases with:
- `host`, `url`, `method`, `headers`, `requestType`, `data` — request definition
- `dependence_case_data` — dependency chain with JSONPath extraction and cache
- `current_request_set_cache` — cache current request/response data
- `assert` — assertions with JSONPath, comparison type, expected value, optional SQL source
- `setup_sql` / `teardown_sql` — pre/post SQL operations
- `teardown` — cleanup API calls with `param_prepare` and `send_request`

### Dynamic Value System

In YAML data fields:
- `${{host()}}` — resolves to configured host URL
- `${{func_name()}}` — calls functions (e.g., random data via Faker)
- `$cache{cache_name}` — references cached values from prior test cases
- JSONPath `$.path.to.field` — extracts nested data from responses

### Configuration

- **`common/config.yaml`** — hosts, notification settings, MySQL connection, environment config. Contains sensitive webhook/DB credentials — do not commit real values.
- **`pytest.ini`** — test discovery paths, markers (`smoke`, `回归测试`)
- **`common/setting.py`** — path resolution with env var overrides

### Test Ordering

`test_case/conftest.py` defines explicit test execution order via `pytest_collection_modifyitems` with an `appoint_items` list. Tests listed there run in that order; unlisted tests run in default collection order.

## Key Dependencies

Python >=3.8, pytest 8.4.1, pydantic 2.x, requests, PyYAML, allure-pytest, jsonpath, Faker, PyMySQL, xlwings. Optional: mitmproxy, redis, pytest-xdist.

Prerequisites for full workflow: JDK and Allure CLI (for report generation).
