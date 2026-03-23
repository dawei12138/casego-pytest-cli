#!/usr/bin/env python
# -*- coding: utf-8 -*-

import ast
import time

import allure
import pytest
import requests

from common.setting import ensure_path_sep
from utils.cache_process.cache_control import CacheHandler
from utils.other_tools.allure_data.allure_tools import allure_step, allure_step_no
from utils.other_tools.models import TestCase
from utils.read_files_tools.clean_files import del_file
from utils.requests_tool.request_control import cache_regular


@pytest.fixture(scope="session", autouse=False)
def clear_report():
    """Remove report files when caller explicitly enables this fixture."""
    del_file(ensure_path_sep("\\report"))


@pytest.fixture(scope="session", autouse=True)
def work_login_init():
    """Fetch login cookie once per session and cache it for dependent cases."""
    url = "https://www.wanandroid.com/user/login"
    data = {
        "username": 19155530606,
        "password": 123456,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    res = requests.post(url=url, data=data, verify=True, headers=headers)
    response_cookie = res.cookies

    cookies = ""
    for key, value in response_cookie.items():
        cookies += f"{key}={value};"

    CacheHandler.update_cache(cache_name="login_cookie", value=cookies)


def pytest_collection_modifyitems(items):
    """Normalize collected case display names and enforce configured order."""
    for item in items:
        try:
            item.name = item.name.encode("utf-8").decode("unicode_escape")
            item._nodeid = item.nodeid.encode("utf-8").decode("unicode_escape")
        except Exception:
            # Keep original naming when unicode normalization is not applicable.
            pass

    appoint_items = [
        "test_get_user_info",
        "test_collect_addtool",
        "test_Cart_List",
        "test_ADD",
        "test_Guest_ADD",
        "test_Clear_Cart_Item",
    ]

    run_items = []
    for expected in appoint_items:
        for item in items:
            module_item = item.name.split("[")[0]
            if expected == module_item:
                run_items.append(item)

    for ordered_item in run_items:
        run_index = run_items.index(ordered_item)
        items_index = items.index(ordered_item)
        if run_index != items_index:
            current_item = items[run_index]
            run_index = items.index(current_item)
            items[items_index], items[run_index] = items[run_index], items[items_index]


def pytest_configure(config):
    config.addinivalue_line("markers", "smoke")
    config.addinivalue_line("markers", "回归测试")


@pytest.fixture(scope="function", autouse=True)
def case_skip(in_data):
    """Skip test case when is_run evaluates to False."""
    in_data = TestCase(**in_data)
    if ast.literal_eval(cache_regular(str(in_data.is_run))) is False:
        allure.dynamic.title(in_data.detail)
        allure_step_no(f"Request URL: {in_data.url}")
        allure_step_no(f"Request method: {in_data.method}")
        allure_step("Headers", in_data.headers)
        allure_step("Request body", in_data.data)
        allure_step("Dependence data", in_data.dependence_case_data)
        allure_step("Assert data", in_data.assert_data)
        pytest.skip()


def pytest_terminal_summary(terminalreporter):
    """Emit a stable terminal summary without relying on external log handlers."""
    passed = len([i for i in terminalreporter.stats.get("passed", []) if i.when != "teardown"])
    errors = len([i for i in terminalreporter.stats.get("error", []) if i.when != "teardown"])
    failed = len([i for i in terminalreporter.stats.get("failed", []) if i.when != "teardown"])
    skipped = len([i for i in terminalreporter.stats.get("skipped", []) if i.when != "teardown"])
    total = terminalreporter._numcollected

    start_time = getattr(terminalreporter, "_sessionstarttime", None)
    if start_time is None:
        session_start = getattr(terminalreporter, "_session_start", None)
        if hasattr(session_start, "timestamp"):
            start_time = session_start.timestamp()
        elif isinstance(session_start, (int, float)):
            start_time = float(session_start)
    if start_time is None:
        start_time = time.time()

    duration = time.time() - start_time
    pass_rate = (passed / total * 100) if total else 0.0

    summary_lines = [
        "",
        "=== Case Summary ===",
        f"total: {total}",
        f"errors: {errors}",
        f"failed: {failed}",
        f"skipped: {skipped}",
        "duration_seconds: %.2f" % duration,
        "pass_rate: %.2f%%" % pass_rate,
    ]
    for line in summary_lines:
        terminalreporter.write_line(line)
