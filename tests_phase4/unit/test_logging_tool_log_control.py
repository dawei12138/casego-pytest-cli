import importlib
import sys
from pathlib import Path

from pytest_auto_api2.utils.logging_tool.log_control import LogHandler


def test_log_handler_creates_parent_directory_for_missing_log_path(tmp_path):
    log_path = tmp_path / "runtime" / "logs" / "info.log"

    handler = LogHandler(str(log_path))
    handler.logger.info("hello")

    assert log_path.parent.exists()
    assert log_path.is_file()


def test_log_control_import_does_not_require_project_config(tmp_path, monkeypatch):
    monkeypatch.setenv("PYTEST_AUTO_API2_HOME", str(tmp_path))

    for module_name in (
        "pytest_auto_api2.utils.logging_tool.log_control",
        "pytest_auto_api2.utils.logging_tool",
        "pytest_auto_api2.utils",
    ):
        sys.modules.pop(module_name, None)

    module = importlib.import_module("pytest_auto_api2.utils.logging_tool.log_control")

    assert hasattr(module, "INFO")


def test_temporary_runtime_loggers_restores_previous_targets(tmp_path):
    from pytest_auto_api2.utils.logging_tool import log_control as log_control_module

    original_paths = {
        "info": Path(log_control_module.INFO.log_path),
        "error": Path(log_control_module.ERROR.log_path),
        "warning": Path(log_control_module.WARNING.log_path),
    }
    target_root = tmp_path / "runtime-root"

    with log_control_module.temporary_runtime_loggers(target_root) as rebound:
        assert Path(log_control_module.INFO.log_path) == rebound["info"]
        assert Path(log_control_module.ERROR.log_path) == rebound["error"]
        assert Path(log_control_module.WARNING.log_path) == rebound["warning"]

    assert Path(log_control_module.INFO.log_path) == original_paths["info"]
    assert Path(log_control_module.ERROR.log_path) == original_paths["error"]
    assert Path(log_control_module.WARNING.log_path) == original_paths["warning"]
