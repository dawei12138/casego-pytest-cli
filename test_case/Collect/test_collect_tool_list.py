#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time   : 2026-03-23 12:52:53


import ast
import allure
import pytest
from pytest_auto_api2.runtime.api import Assert, RequestControl, TearDownHandler, regular
from pytest_auto_api2.runtime.loader import build_case_cache, load_cases_by_ids


case_id = ['collect_tool_list_01']
build_case_cache()
TestData = load_cases_by_ids(case_id)
re_data = regular(str(TestData))


@allure.epic("开发平台接口")
@allure.feature("收藏模块")
class TestCollectToolList:

    @allure.story("收藏网址列表接口")
    @pytest.mark.parametrize('in_data', ast.literal_eval(re_data), ids=[i['detail'] for i in TestData])
    def test_collect_tool_list(self, in_data, case_skip):
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
    pytest.main(['test_collect_tool_list.py', '-s', '-W', 'ignore:Module already imported:pytest.PytestWarning'])
