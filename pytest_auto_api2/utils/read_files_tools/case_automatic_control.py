#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
# @Time   : 2022/3/28 13:22
# @Author : 浣欏皯鐞?
"""
import os
from pathlib import Path
from typing import Text

from pytest_auto_api2.common.setting import data_dir_path, test_case_dir_path, resolve_project_path
from pytest_auto_api2.utils.read_files_tools.get_all_files_path import get_all_files
from pytest_auto_api2.utils.read_files_tools.testcase_template import write_testcase_file
from pytest_auto_api2.utils.read_files_tools.yaml_control import GetYamlData


class TestCaseAutomaticGeneration:
    def __init__(self, *, data_dir: Text = None, test_dir: Text = None, force_write: bool = False):
        self.yaml_case_data = None
        self.file_path = None
        self._data_dir = resolve_project_path(data_dir) if data_dir else data_dir_path()
        self._test_dir = resolve_project_path(test_dir) if test_dir else test_case_dir_path()
        self._force_write = force_write

    @property
    def case_date_path(self) -> Text:
        """Return yaml testcase directory path."""
        return self._data_dir

    @property
    def case_path(self) -> Text:
        """Return generated pytest testcase directory path."""
        return self._test_dir

    @property
    def allure_epic(self):
        _allure_epic = self.yaml_case_data.get("case_common").get("allureEpic")
        assert _allure_epic is not None, (
            "鐢ㄤ緥涓?allureEpic 涓哄繀濉」锛岃妫€鏌ョ敤渚嬪唴瀹? 鐢ㄤ緥璺緞锛?%s'" % self.file_path
        )
        return _allure_epic

    @property
    def allure_feature(self):
        _allure_feature = self.yaml_case_data.get("case_common").get("allureFeature")
        assert _allure_feature is not None, (
            "鐢ㄤ緥涓?allureFeature 涓哄繀濉」锛岃妫€鏌ョ敤渚嬪唴瀹? 鐢ㄤ緥璺緞锛?%s'" % self.file_path
        )
        return _allure_feature

    @property
    def allure_story(self):
        _allure_story = self.yaml_case_data.get("case_common").get("allureStory")
        assert _allure_story is not None, (
            "鐢ㄤ緥涓?allureStory 涓哄繀濉」锛岃妫€鏌ョ敤渚嬪唴瀹? 鐢ㄤ緥璺緞锛?%s'" % self.file_path
        )
        return _allure_story

    @property
    def file_name(self) -> Text:
        """
        Convert current yaml file path to relative python path.
        Example: Collect/collect_tool_list.yaml -> Collect/collect_tool_list.py
        """
        relative = os.path.relpath(self.file_path, self.case_date_path)
        filename, ext = os.path.splitext(relative)
        if ext.lower() not in {".yaml", ".yml"}:
            return relative
        return filename + ".py"

    @property
    def get_test_class_title(self):
        """Generate class name from case filename."""
        _file_name = os.path.split(self.file_name)[1][:-3]
        _name = _file_name.split("_")
        for index in range(len(_name)):
            _name[index] = _name[index].capitalize()
        return "".join(_name)

    @property
    def func_title(self) -> Text:
        """Generate test function name from case filename."""
        return os.path.split(self.file_name)[1][:-3]

    @property
    def spilt_path(self):
        path = self.file_name.split(os.sep)
        path[-1] = "test_" + path[-1]
        return path

    @property
    def get_case_path(self):
        """Return generated target testcase file absolute path."""
        return os.path.join(self.case_path, *self.spilt_path)

    @property
    def case_ids(self):
        return [key for key in self.yaml_case_data.keys() if key != "case_common"]

    @property
    def get_file_name(self):
        return self.spilt_path[-1]

    def mk_dir(self) -> None:
        """Create target test directory if missing."""
        case_dir_path = os.path.split(self.get_case_path)[0]
        if not os.path.exists(case_dir_path):
            os.makedirs(case_dir_path)

    def get_case_automatic(self) -> None:
        """Generate pytest test files from all yaml cases."""
        data_path = Path(self.case_date_path)
        if not data_path.exists():
            raise FileNotFoundError(f"YAML data directory does not exist: {data_path}")

        file_paths = get_all_files(file_path=str(data_path), yaml_data_switch=True)
        for file in file_paths:
            if "proxy_data.yaml" in file:
                continue

            self.yaml_case_data = GetYamlData(file).get_yaml_data()
            self.file_path = file
            self.mk_dir()
            write_testcase_file(
                allure_epic=self.allure_epic,
                allure_feature=self.allure_feature,
                class_title=self.get_test_class_title,
                func_title=self.func_title,
                case_path=self.get_case_path,
                case_ids=self.case_ids,
                file_name=self.get_file_name,
                allure_story=self.allure_story,
                force_write=self._force_write,
            )


if __name__ == "__main__":
    TestCaseAutomaticGeneration().get_case_automatic()
