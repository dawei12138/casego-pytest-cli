#!/usr/bin/env python
# -*- coding: utf-8 -*-

import json

from utils.cache_process import cache_control
from utils.cache_process.cache_control import CacheHandler
from utils.other_tools.models import DependentCaseData, DependentData, SendRequest, TestCase as ApiCaseModel
from utils.requests_tool import dependent_case as dependent_case_module
from utils.requests_tool.dependent_case import DependentCase
from utils.requests_tool.teardown_control import TearDownHandler


def test_dependent_case_replace_value_supports_prefix(monkeypatch):
    cache_control._cache_config.clear()

    class DummyRequestControl:
        def __init__(self, *_args, **_kwargs):
            pass

        @staticmethod
        def http_request():
            class DummyResponse:
                response_data = json.dumps({"token": "abc123"})
                body = {}

            return DummyResponse()

    monkeypatch.setattr(dependent_case_module, "RequestControl", DummyRequestControl)
    CacheHandler.update_cache(cache_name="login_01", value={"case_id": "login_01"})

    case = ApiCaseModel(
        url="https://api.example.com/user/info",
        method="GET",
        detail="dependent replacement",
        assert_data={"status_code": 200},
        headers={"Authorization": ""},
        requestType="NONE",
        is_run=True,
        data=None,
        dependence_case=True,
        dependence_case_data=[
            DependentCaseData(
                case_id="login_01",
                dependent_data=[
                    DependentData(
                        dependent_type="response",
                        jsonpath="$.token",
                        set_cache="token",
                        replace_key="$.headers.Authorization",
                        replace_value="Bearer $cache{token}",
                    )
                ],
            )
        ],
    )

    DependentCase(case).get_dependent_data()

    assert case.headers["Authorization"] == "Bearer abc123"
    assert CacheHandler.get_cache("token") == "abc123"


def test_teardown_cache_replace_value_supports_prefix():
    cache_control._cache_config.clear()
    CacheHandler.update_cache(cache_name="token", value="xyz")

    teardown_case_payload = {"headers": {"Authorization": ""}}
    teardown_case = SendRequest(
        dependent_type="cache",
        cache_data="token",
        replace_key="$.headers.Authorization",
        replace_value="Bearer $cache{token}",
    )

    TearDownHandler.dependent_type_cache(
        teardown_case=teardown_case,
        teardown_case_payload=teardown_case_payload,
    )

    assert teardown_case_payload["headers"]["Authorization"] == "Bearer xyz"


def test_dependent_case_without_replace_value_uses_extracted_value(monkeypatch):
    cache_control._cache_config.clear()

    class DummyRequestControl:
        def __init__(self, *_args, **_kwargs):
            pass

        @staticmethod
        def http_request():
            class DummyResponse:
                response_data = json.dumps({"token": "raw-token"})
                body = {}

            return DummyResponse()

    monkeypatch.setattr(dependent_case_module, "RequestControl", DummyRequestControl)
    CacheHandler.update_cache(cache_name="login_01", value={"case_id": "login_01"})

    case = ApiCaseModel(
        url="https://api.example.com/user/info",
        method="GET",
        detail="dependent replacement",
        assert_data={"status_code": 200},
        headers={"Authorization": ""},
        requestType="NONE",
        is_run=True,
        data=None,
        dependence_case=True,
        dependence_case_data=[
            DependentCaseData(
                case_id="login_01",
                dependent_data=[
                    DependentData(
                        dependent_type="response",
                        jsonpath="$.token",
                        replace_key="$.headers.Authorization",
                    )
                ],
            )
        ],
    )

    DependentCase(case).get_dependent_data()

    assert case.headers["Authorization"] == "raw-token"
