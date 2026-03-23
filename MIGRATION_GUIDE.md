# Migration Guide to `pytest_auto_api2`

This guide describes how to migrate from the repository-bound layout to the namespaced CLI/runtime flow.

## 1. Install/Upgrade CLI

```bash
python -m pip install -e . --no-build-isolation --no-deps
```

The command entrypoint is:

```bash
api2 --help
```

## 2. New Runtime Namespace

Generated test files now import runtime helpers from:

- `pytest_auto_api2.runtime.api`
- `pytest_auto_api2.runtime.loader`

This removes direct imports of project-relative `utils.*` paths from generated test modules.

## 3. Directory and Config Overrides

You can now run with custom paths:

```bash
api2 gen --project-root D:\\myproj --config conf\\qa.yaml --data-dir cases --test-dir out_tests
api2 run --project-root D:\\myproj --data-dir cases --test-dir out_tests -k smoke
```

Equivalent environment variables:

- `PYTEST_AUTO_API2_HOME`
- `PYTEST_AUTO_API2_CONFIG`
- `PYTEST_AUTO_API2_DATA_DIR`
- `PYTEST_AUTO_API2_TEST_DIR`

## 4. Initialize a New Project Anywhere

```bash
api2 init D:\\my-new-api2-project
```

This creates:

- `common/config.yaml`
- `data/demo_banner.yaml`
- `test_case/__init__.py`
- `test_case/conftest.py`
- `pytest.ini`

Use `--force` to overwrite scaffold files.

## 5. Compatibility Notes

- Existing `cli.py` remains as a compatibility shim and forwards to `pytest_auto_api2.cli`.
- Existing repository structure still works.
- `run.py` remains available for legacy workflow.

## 6. Recommended New Workflow

```bash
api2 gen --project-root .
api2 run --project-root . -m smoke
api2 all --project-root . --allure --generate-report
```
