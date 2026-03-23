# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

pytest-auto-api2 is a data-driven API automated testing framework (Python + pytest + Allure). Test cases are defined in YAML files under `data/`, auto-generated into Python test code under `test_case/`, and executed via pytest. The framework supports multi-interface dependencies, database assertions, dynamic value replacement, and multi-channel notifications.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run all tests with Allure report generation and notifications
python run.py

# Run tests directly via pytest
pytest -s test_case/

# Run only smoke-marked tests
pytest -s test_case/ -m smoke

# Auto-generate Python test code from YAML definitions
python utils/read_files_tools/case_automatic_control.py
```

## Architecture

### Execution Flow

1. YAML test cases in `data/` are parsed and loaded into a case pool (`test_case/__init__.py`)
2. Python test files in `test_case/` are auto-generated from YAML via `case_automatic_control.py`
3. Session fixtures in `test_case/conftest.py` handle login/init
4. Each test: resolve dependencies → execute HTTP request → run assertions → teardown cleanup
5. `run.py` orchestrates: pytest execution → Allure report → notifications

### Key Modules

- **`utils/requests_tool/request_control.py`** — `RequestControl` class: HTTP request wrapper (GET/POST/PUT/DELETE/PATCH), handles content types (JSON, form-data, multipart, file upload)
- **`utils/requests_tool/dependent_case.py`** — `DependentCase`: resolves multi-level case dependencies (Case A response → Case B request) using JSONPath extraction
- **`utils/assertion/assert_control.py`** — `AssertUtil`: response assertions (JSONPath-based), database assertions (SQL query comparison), supports operators: `==`, `!=`, `<`, `>`, `in`, `not_in`, regex
- **`utils/read_files_tools/regular_control.py`** — Dynamic value replacement: `${{func_name()}}` for functions, `$cache{name}` for cache references
- **`utils/read_files_tools/get_yaml_data_analysis.py`** — Parses and validates YAML test case structure into Pydantic models
- **`utils/other_tools/models.py`** — Pydantic data models (`TestCase`, `DependentData`, `ResponseData`, etc.) and enums (`RequestType`, `Method`, `DependentType`)
- **`utils/cache_process/cache_control.py`** — In-memory dict-based cache for sharing data between test cases (tokens, extracted values)
- **`utils/requests_tool/teardown_control.py`** — Post-test cleanup via API calls or SQL execution

### YAML Test Case Structure

Each YAML file in `data/` contains `case_common` (Allure metadata) and individual cases with:
- `host`, `url`, `method`, `headers`, `requestType`, `data` — request definition
- `dependence_case_data` — dependency chain with JSONPath extraction and cache
- `current_request_set_cache` — cache current request/response data
- `assert` — assertions with JSONPath, comparison type, expected value, optional SQL source
- `setup_sql` / `teardown_sql` — pre/post SQL operations
- `teardown` — cleanup API calls with `param_prepare` and `send_request`

### Configuration

- **`common/config.yaml`** — hosts, notification settings (DingTalk/WeChat/Email/Lark), MySQL connection, environment config
- **`pytest.ini`** — test discovery paths, markers (`smoke`, `回归测试`)
- **`common/setting.py`** — path constants and environment settings

### Dynamic Value System

In YAML data fields:
- `${{host()}}` — resolves to configured host URL
- `${{func_name()}}` — calls functions (e.g., random data via Faker)
- `$cache{cache_name}` — references cached values from prior test cases
- JSONPath `$.path.to.field` — extracts nested data from responses

## Key Dependencies

pytest 7.1.2, requests, PyYAML, pydantic 1.8.2, allure-pytest, jsonpath, Faker, PyMySQL, redis, mitmproxy
