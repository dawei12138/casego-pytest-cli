
from utils.read_files_tools.yaml_control import GetYamlData
from common.setting import config_path
from utils.other_tools.models import Config


_data = GetYamlData(config_path()).get_yaml_data()
config = Config(**_data)

