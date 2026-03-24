#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""
# @Time    : 2022/5/23 14:22
# @Author  : 浣欏皯鐞?
# @Email   : 1603453211@qq.com
# @File    : teardownControl
# @describe: request teardown handling
"""
import ast
import json
from typing import Any, Dict, Text, Union, List

from jsonpath import jsonpath

from pytest_auto_api2.utils import config
from pytest_auto_api2.utils.cache_process.cache_control import CacheHandler
from pytest_auto_api2.utils.logging_tool.log_control import WARNING
from pytest_auto_api2.utils.mysql_tool.mysql_control import MysqlDB
from pytest_auto_api2.utils.other_tools.exceptions import JsonpathExtractionFailed, ValueNotFoundError
from pytest_auto_api2.utils.other_tools.models import ResponseData, TearDown, SendRequest, ParamPrepare
from pytest_auto_api2.utils.read_files_tools.regular_control import cache_regular, sql_regular, regular
from pytest_auto_api2.utils.requests_tool.request_control import RequestControl


class TearDownHandler:
    """Handle yaml teardown requests."""

    def __init__(self, res: "ResponseData"):
        self._res = res

    @staticmethod
    def parse_jsonpath_tokens(expr: Text) -> List[Union[Text, int]]:
        """Parse minimal jsonpath syntax: $.data.items[0].id."""
        if not isinstance(expr, str) or not expr.startswith("$."):
            raise ValueError(f"invalid jsonpath expression: {expr}")

        body = expr[2:]
        tokens: List[Union[Text, int]] = []
        buffer = ""
        index = 0

        while index < len(body):
            char = body[index]
            if char == ".":
                if buffer:
                    tokens.append(buffer)
                    buffer = ""
                index += 1
                continue

            if char == "[":
                if buffer:
                    tokens.append(buffer)
                    buffer = ""

                end = body.find("]", index)
                if end == -1:
                    raise ValueError(f"invalid jsonpath bracket syntax: {expr}")

                segment = body[index + 1:end].strip()
                if segment.isdigit():
                    tokens.append(int(segment))
                else:
                    tokens.append(segment.strip("'\""))
                index = end + 1
                continue

            buffer += char
            index += 1

        if buffer:
            tokens.append(buffer)
        if not tokens:
            raise ValueError(f"invalid jsonpath expression: {expr}")
        return tokens

    @staticmethod
    def _get_container_value(container: Any, token: Union[Text, int]) -> Any:
        if isinstance(token, int):
            return container[token]
        if isinstance(container, dict):
            return container[token]
        if hasattr(container, token):
            return getattr(container, token)
        raise KeyError(f"token not found: {token}")

    @staticmethod
    def _set_container_value(container: Any, token: Union[Text, int], value: Any) -> None:
        if isinstance(token, int):
            container[token] = value
            return
        if isinstance(container, dict):
            container[token] = value
            return
        if hasattr(container, token):
            setattr(container, token, value)
            return
        raise KeyError(f"token not found: {token}")

    @classmethod
    def jsonpath_replace_data(cls, replace_key: Text, replace_value: Any, teardown_case: Dict) -> None:
        """Replace value in teardown case by jsonpath path key."""
        tokens = cls.parse_jsonpath_tokens(replace_key)
        current: Any = teardown_case
        for token in tokens[:-1]:
            current = cls._get_container_value(current, token)
        cls._set_container_value(current, tokens[-1], replace_value)

    @classmethod
    def get_cache_name(cls, replace_key: Text, resp_case_data: Dict) -> None:
        """Extract cache name from expression and write cache value."""
        if "$set_cache{" in replace_key and "}" in replace_key:
            start_index = replace_key.index("$set_cache{")
            end_index = replace_key.index("}", start_index)
            old_value = replace_key[start_index:end_index + 2]
            cache_name = old_value[11:old_value.index("}")]
            CacheHandler.update_cache(cache_name=cache_name, value=resp_case_data)

    @classmethod
    def regular_testcase(cls, teardown_case: Dict) -> Dict:
        """Handle dynamic placeholders in testcase payload."""
        test_case = regular(str(teardown_case))
        return ast.literal_eval(cache_regular(str(test_case)))

    @staticmethod
    def resolve_replace_value(default_value: Any, raw_replace_value: Any) -> Any:
        """Resolve final replacement value with optional cache/dynamic placeholders."""
        if raw_replace_value is None:
            return default_value
        if isinstance(raw_replace_value, str):
            return cache_regular(regular(raw_replace_value))
        return raw_replace_value

    @classmethod
    def teardown_http_requests(cls, teardown_case: Dict) -> "ResponseData":
        """Send teardown request."""
        test_case = cls.regular_testcase(teardown_case)
        return RequestControl(test_case).http_request(dependent_switch=False)

    def dependent_type_response(
        self,
        teardown_case_data: "SendRequest",
        resp_data: Dict,
        teardown_case: Dict,
    ) -> None:
        """Replace teardown request payload from response jsonpath data."""
        replace_key = teardown_case_data.replace_key
        response_dependent = jsonpath(obj=resp_data, expr=teardown_case_data.jsonpath)

        if response_dependent is not False:
            replace_value = self.resolve_replace_value(
                default_value=response_dependent[0],
                raw_replace_value=teardown_case_data.replace_value,
            )
            self.jsonpath_replace_data(
                replace_key=replace_key,
                replace_value=replace_value,
                teardown_case=teardown_case,
            )
        else:
            raise JsonpathExtractionFailed(
                f"jsonpath extraction failed. object={resp_data}, jsonpath={teardown_case_data.jsonpath}"
            )

    def dependent_type_request(self, teardown_case_data: "SendRequest", request_data: Dict) -> None:
        """Handle teardown request dependency based on original request payload."""
        try:
            set_value = teardown_case_data.set_cache
            request_dependent = jsonpath(obj=request_data, expr=teardown_case_data.jsonpath)
            if request_dependent is not False:
                request_case_data = request_dependent[0]
                self.get_cache_name(replace_key=set_value, resp_case_data=request_case_data)
            else:
                raise JsonpathExtractionFailed(
                    f"jsonpath extraction failed. object={request_data}, jsonpath={teardown_case_data.jsonpath}"
                )
        except AttributeError as exc:
            raise ValueNotFoundError("teardown request dependency missing set_cache/jsonpath") from exc

    def dependent_self_response(
        self,
        teardown_case_data: "ParamPrepare",
        res: Dict,
        resp_data: Dict,
    ) -> None:
        """Handle dependency from teardown case self response."""
        try:
            set_value = teardown_case_data.set_cache
            response_dependent = jsonpath(obj=res, expr=teardown_case_data.jsonpath)

            if response_dependent is not False:
                resp_case_data = response_dependent[0]
                CacheHandler.update_cache(cache_name=set_value, value=resp_case_data)
                self.get_cache_name(replace_key=set_value, resp_case_data=resp_case_data)
            else:
                raise JsonpathExtractionFailed(
                    f"jsonpath extraction failed. object={resp_data}, jsonpath={teardown_case_data.jsonpath}"
                )
        except AttributeError as exc:
            raise ValueNotFoundError("teardown param_prepare dependency missing set_cache/jsonpath") from exc

    @classmethod
    def dependent_type_cache(cls, teardown_case: "SendRequest", teardown_case_payload: Dict) -> None:
        """Replace teardown request payload from cache value."""
        if teardown_case.dependent_type != "cache":
            return

        cache_name = teardown_case.cache_data
        replace_key = teardown_case.replace_key
        value_types = ["int:", "bool:", "list:", "dict:", "tuple:", "float:"]

        if any(prefix in cache_name for prefix in value_types):
            cache_value = CacheHandler.get_cache(cache_name.split(":", 1)[1])
        else:
            cache_value = str(CacheHandler.get_cache(cache_name))

        replace_value = cls.resolve_replace_value(
            default_value=cache_value,
            raw_replace_value=teardown_case.replace_value,
        )

        cls.jsonpath_replace_data(
            replace_key=replace_key,
            replace_value=replace_value,
            teardown_case=teardown_case_payload,
        )

    def send_request_handler(self, data: "TearDown", resp_data: Dict, request_data: Dict) -> None:
        """Handle teardown send_request branch."""
        send_request = data.send_request
        case_id = data.case_id
        teardown_case_payload = CacheHandler.get_cache(case_id)

        for item in send_request:
            if item.dependent_type == "cache":
                self.dependent_type_cache(teardown_case=item, teardown_case_payload=teardown_case_payload)
            if item.dependent_type == "response":
                self.dependent_type_response(
                    teardown_case_data=item,
                    resp_data=resp_data,
                    teardown_case=teardown_case_payload,
                )
            elif item.dependent_type == "request":
                self.dependent_type_request(teardown_case_data=item, request_data=request_data)

        test_case = self.regular_testcase(teardown_case_payload)
        self.teardown_http_requests(test_case)

    def param_prepare_request_handler(self, data: "TearDown", resp_data: Dict) -> None:
        """Handle teardown param_prepare branch."""
        case_id = data.case_id
        teardown_case_payload = CacheHandler.get_cache(case_id)
        param_prepare = data.param_prepare
        res = self.teardown_http_requests(teardown_case_payload)

        for item in param_prepare:
            if item.dependent_type == "self_response":
                self.dependent_self_response(
                    teardown_case_data=item,
                    resp_data=resp_data,
                    res=json.loads(res.response_data),
                )

    def teardown_handle(self) -> None:
        """Main teardown entrypoint."""
        teardown_data = self._res.teardown
        resp_data = self._res.response_data
        request_data = self._res.yaml_data.data

        if teardown_data is not None:
            for data in teardown_data:
                if data.param_prepare is not None:
                    self.param_prepare_request_handler(data=data, resp_data=json.loads(resp_data))
                elif data.send_request is not None:
                    self.send_request_handler(
                        data=data,
                        request_data=request_data,
                        resp_data=json.loads(resp_data),
                    )

        self.teardown_sql()

    def teardown_sql(self) -> None:
        """Handle teardown sql branch."""
        sql_data = self._res.teardown_sql
        response_data = self._res.response_data

        if sql_data is not None:
            for sql in sql_data:
                if config.mysql_db.switch:
                    sql_data_real = sql_regular(value=sql, res=json.loads(response_data))
                    MysqlDB().execute(cache_regular(sql_data_real))
                else:
                    WARNING.logger.warning(
                        "mysql switch is off, skip teardown sql: %s", sql
                    )
