
from pytest_auto_api2.utils.read_files_tools.yaml_control import GetYamlData
from pytest_auto_api2.common.setting import config_path
from pytest_auto_api2.utils.other_tools.models import Config


_data = GetYamlData(config_path()).get_yaml_data()
config = Config(**_data)

