#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""
# @Time    : 2022/4/25 20:02
# @Author  : 浣欏皯鐞?
# @Email   : 1603453211@qq.com
# @File    : testcase_template
# @describe: 鐢ㄤ緥妯℃澘
"""

import datetime
import json
import os
from utils.read_files_tools.yaml_control import GetYamlData
from common.setting import config_path
from utils.other_tools.exceptions import ValueNotFoundError


def write_case(case_path, page):
    """ 鍐欏叆鐢ㄤ緥鏁版嵁 """
    with open(case_path, 'w', encoding="utf-8") as file:
        file.write(page)


def _py_string_literal(value):
    """Render a safe Python string literal for generated decorators."""
    if value is None:
        value = ""
    return json.dumps(str(value), ensure_ascii=False)


def write_testcase_file(*, allure_epic, allure_feature, class_title,
                        func_title, case_path, case_ids, file_name, allure_story,
                        force_write=False):
    """

        :param allure_story:
        :param file_name: 鏂囦欢鍚嶇О
        :param allure_epic: 椤圭洰鍚嶇О
        :param allure_feature: 妯″潡鍚嶇О
        :param class_title: 绫诲悕绉?
        :param func_title: 鍑芥暟鍚嶇О
        :param case_path: case 璺緞
        :param case_ids: 鐢ㄤ緥ID
        :return:
        """
    conf_data = GetYamlData(config_path()).get_yaml_data()
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    real_time_update_test_cases = conf_data['real_time_update_test_cases']
    allure_epic_literal = _py_string_literal(allure_epic)
    allure_feature_literal = _py_string_literal(allure_feature)
    allure_story_literal = _py_string_literal(allure_story)

    page = f'''#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time   : {now}


import ast
import allure
import pytest
from pytest_auto_api2.runtime.api import Assert, RequestControl, TearDownHandler, regular
from pytest_auto_api2.runtime.loader import build_case_cache, load_cases_by_ids


case_id = {case_ids}
build_case_cache()
TestData = load_cases_by_ids(case_id)
re_data = regular(str(TestData))


@allure.epic({allure_epic_literal})
@allure.feature({allure_feature_literal})
class Test{class_title}:

    @allure.story({allure_story_literal})
    @pytest.mark.parametrize('in_data', ast.literal_eval(re_data), ids=[i['detail'] for i in TestData])
    def test_{func_title}(self, in_data, case_skip):
        """
        :param :
        :return:
        """
        res = RequestControl(in_data).http_request()
        TearDownHandler(res).teardown_handle()
        Assert(assert_data=in_data['assert_data'],
               sql_data=res.sql_data,
               request_data=res.body,
               response_data=res.response_data,
               status_code=res.status_code).assert_type_handle()


if __name__ == '__main__':
    pytest.main(['{file_name}', '-s', '-W', 'ignore:Module already imported:pytest.PytestWarning'])
'''
    if force_write:
        write_case(case_path=case_path, page=page)
    elif real_time_update_test_cases:
        write_case(case_path=case_path, page=page)
    elif real_time_update_test_cases is False:
        if not os.path.exists(case_path):
            write_case(case_path=case_path, page=page)
    else:
        raise ValueNotFoundError("real_time_update_test_cases 閰嶇疆涓嶆纭紝鍙兘閰嶇疆 True 鎴栬€?False")
