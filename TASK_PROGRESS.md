# Project Task Progress

Last updated: 2026-03-23 (Phase 1 + Phase 2 + Phase 3 completed)

| Phase | Task ID | Task | Status | Notes |
| --- | --- | --- | --- | --- |
| Phase 1 | P1-1 | Add packaging metadata (`pyproject.toml`) and register CLI command entrypoint | Completed | Added `pyproject.toml` and CLI script registration |
| Phase 1 | P1-2 | Implement CLI command module with `gen` / `run` / `all` subcommands | Completed | Added command dispatch and arguments |
| Phase 1 | P1-3 | Add project-root environment variable support for path resolution | Completed | Added `PYTEST_AUTO_API2_HOME` support in path resolver |
| Phase 1 | P1-4 | Add run-time options for pytest target execution and report controls | Completed | Added pytest selection/allure/report/notify options |
| Phase 1 | P1-5 | Smoke-check CLI command parsing and help output | Completed | Verified help output, `gen` execution and installable command |
| Phase 2 | P2-1 | Refactor code to namespaced installable package structure (`pytest_auto_api2`) | Completed | Added `pytest_auto_api2` package, moved main CLI to package namespace |
| Phase 2 | P2-2 | Decouple generated test imports from repository-relative modules | Completed | Generated template now imports runtime bridge modules under namespace |
| Phase 2 | P2-3 | Add `api2 init` to scaffold a runnable project template in any directory | Completed | Added `api2 init [path]` with scaffold file generation |
| Phase 2 | P2-4 | Support external config path and explicit data/test directories in CLI | Completed | Added `--config/--data-dir/--test-dir` and env bindings |
| Phase 2 | P2-5 | Add migration guide from current repository layout to package layout | Completed | Added `MIGRATION_GUIDE.md` |
| Phase 3 | P3-1 | Add unit tests for CLI argument parsing and command dispatch | Completed | Added `tests_phase3/unit/test_cli_unit.py` |
| Phase 3 | P3-2 | Add integration tests for YAML->pytest generation and filtered runs | Completed | Added `tests_phase3/integration/test_cli_integration.py`; 5 tests passed |
| Phase 3 | P3-3 | Add CI workflow for lint/test/package build checks | Completed | Added `.github/workflows/ci.yml` |
| Phase 3 | P3-4 | Add release process docs and versioning strategy | Completed | Added `RELEASE_PROCESS.md` |
| Phase 3 | P3-5 | Publish package to internal or public index and verify install flow | Completed | Added `.github/workflows/publish.yml`; built dist and verified wheel install locally |
