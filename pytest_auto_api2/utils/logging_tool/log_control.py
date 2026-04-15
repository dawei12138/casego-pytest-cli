#!/usr/bin/env python
# -*- coding: utf-8 -*-

from contextlib import contextmanager
import logging
import time
from logging import handlers
from pathlib import Path
from typing import Dict, Iterator, Text

import colorlog

from pytest_auto_api2.common.setting import ensure_path_sep


class LogHandler:
    """Runtime log wrapper with rebinding support."""

    level_relations = {
        "debug": logging.DEBUG,
        "info": logging.INFO,
        "warning": logging.WARNING,
        "error": logging.ERROR,
        "critical": logging.CRITICAL,
    }

    def __init__(
        self,
        filename: Text,
        level: Text = "info",
        when: Text = "D",
        fmt: Text = "%(levelname)-8s%(asctime)s%(name)s:%(filename)s:%(lineno)d %(message)s",
    ):
        self.level = level
        self.when = when
        self.fmt = fmt
        self.logger = logging.getLogger(str(Path(filename).resolve()))
        self.log_path = str(Path(filename).resolve())
        self._configure_logger(filename)

    @classmethod
    def log_color(cls):
        log_colors_config = {
            "DEBUG": "cyan",
            "INFO": "green",
            "WARNING": "yellow",
            "ERROR": "red",
            "CRITICAL": "red",
        }
        return colorlog.ColoredFormatter(
            "%(log_color)s[%(asctime)s] [%(name)s] [%(levelname)s]: %(message)s",
            log_colors=log_colors_config,
        )

    @staticmethod
    def _remove_handlers(logger: logging.Logger) -> None:
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            if hasattr(handler, "baseFilename"):
                handler.close()

    def _configure_logger(self, filename: Text) -> Path:
        target_path = Path(filename).resolve()
        logger = logging.getLogger(str(target_path))
        self._remove_handlers(self.logger)
        if logger is not self.logger:
            self._remove_handlers(logger)
        logger.setLevel(self.level_relations.get(self.level))
        logger.propagate = False

        screen_output = logging.StreamHandler()
        screen_output.setFormatter(self.log_color())

        target_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = handlers.TimedRotatingFileHandler(
            filename=str(target_path),
            when=self.when,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setFormatter(logging.Formatter(self.fmt))

        logger.addHandler(screen_output)
        logger.addHandler(file_handler)
        self.logger = logger
        self.log_path = str(target_path)
        return target_path

    def rebind(self, filename: Text) -> Path:
        return self._configure_logger(filename)


def _current_day() -> str:
    return time.strftime("%Y-%m-%d", time.localtime())


now_time_day = _current_day()
INFO = LogHandler(ensure_path_sep(f"\\logs\\info-{now_time_day}.log"), level="info")
ERROR = LogHandler(ensure_path_sep(f"\\logs\\error-{now_time_day}.log"), level="error")
WARNING = LogHandler(ensure_path_sep(f"\\logs\\warning-{now_time_day}.log"))


def _daily_log_paths(project_root: Path) -> Dict[str, Path]:
    root = Path(project_root).resolve()
    day = _current_day()
    return {
        "info": root / "logs" / f"info-{day}.log",
        "error": root / "logs" / f"error-{day}.log",
        "warning": root / "logs" / f"warning-{day}.log",
    }


def rebind_runtime_loggers(project_root: Text) -> Dict[str, Path]:
    paths = _daily_log_paths(Path(project_root))
    return {
        "info": INFO.rebind(str(paths["info"])),
        "error": ERROR.rebind(str(paths["error"])),
        "warning": WARNING.rebind(str(paths["warning"])),
    }


def runtime_log_paths() -> Dict[str, Path]:
    return {
        "info": Path(INFO.log_path).resolve(),
        "error": Path(ERROR.log_path).resolve(),
        "warning": Path(WARNING.log_path).resolve(),
    }


@contextmanager
def temporary_runtime_loggers(project_root: Text) -> Iterator[Dict[str, Path]]:
    previous_paths = runtime_log_paths()
    rebound_paths = rebind_runtime_loggers(project_root)
    try:
        yield rebound_paths
    finally:
        INFO.rebind(str(previous_paths["info"]))
        ERROR.rebind(str(previous_paths["error"]))
        WARNING.rebind(str(previous_paths["warning"]))


if __name__ == "__main__":
    ERROR.logger.error("test")
