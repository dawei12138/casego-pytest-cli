from __future__ import annotations

from functools import lru_cache


@lru_cache(maxsize=1)
def get_config():
    from pytest_auto_api2.common.setting import config_path
    from pytest_auto_api2.utils.other_tools.models import Config
    from pytest_auto_api2.utils.read_files_tools.yaml_control import GetYamlData

    data = GetYamlData(config_path()).get_yaml_data()
    return Config(**data)


def __getattr__(name: str):
    if name == "config":
        return get_config()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["config", "get_config"]
