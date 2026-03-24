"""
# @Time   : 2022/3/28 16:08
# @Author : 浣欏皯鐞?
"""
import ast
import json
from typing import Any, Text, Dict, Union, List

from jsonpath import jsonpath

from pytest_auto_api2.utils import config
from pytest_auto_api2.utils.cache_process.cache_control import CacheHandler
from pytest_auto_api2.utils.logging_tool.log_control import WARNING
from pytest_auto_api2.utils.mysql_tool.mysql_control import SetUpMySQL
from pytest_auto_api2.utils.other_tools.exceptions import ValueNotFoundError
from pytest_auto_api2.utils.other_tools.models import DependentType
from pytest_auto_api2.utils.other_tools.models import TestCase, DependentCaseData, DependentData
from pytest_auto_api2.utils.read_files_tools.regular_control import regular, cache_regular
from pytest_auto_api2.utils.requests_tool.request_control import RequestControl


class DependentCase:
    """Handle dependent-case data extraction and replacement."""

    def __init__(self, dependent_yaml_case: TestCase):
        self.__yaml_case = dependent_yaml_case

    @classmethod
    def get_cache(cls, case_id: Text) -> Dict:
        """Get cached case payload by case id."""
        return CacheHandler.get_cache(case_id)

    @classmethod
    def jsonpath_data(cls, obj: Dict, expr: Text) -> list:
        """Extract data by jsonpath expression."""
        extracted = jsonpath(obj, expr)
        if extracted is False:
            raise ValueNotFoundError(
                f"jsonpath extraction failed. object={obj}, jsonpath={expr}"
            )
        return extracted

    @classmethod
    def set_cache_value(cls, dependent_data: "DependentData") -> Union[Text, None]:
        """Get optional cache target key from dependency definition."""
        return getattr(dependent_data, "set_cache", None)

    @classmethod
    def replace_key(cls, dependent_data: "DependentData"):
        """Get optional replacement path key from dependency definition."""
        return getattr(dependent_data, "replace_key", None)

    @classmethod
    def replace_value(cls, dependent_data: "DependentData") -> Any:
        """Get optional replacement value template from dependency definition."""
        return getattr(dependent_data, "replace_value", None)

    @staticmethod
    def _resolve_replace_value(raw_replace_value: Any, extracted: list) -> Any:
        """Resolve final replacement value with optional cache/dynamic placeholders."""
        if raw_replace_value is None:
            return extracted[0]
        if isinstance(raw_replace_value, str):
            return cache_regular(regular(raw_replace_value))
        return raw_replace_value

    def url_replace(self, replace_key: Text, jsonpath_dates: Dict, replace_value: Any) -> None:
        """Handle url replacement helpers."""
        if "$url_param" in replace_key:
            replaced_url = self.__yaml_case.url.replace(replace_key, str(replace_value))
            jsonpath_dates["$.url"] = replaced_url
        else:
            jsonpath_dates[replace_key] = replace_value

    @staticmethod
    def _parse_jsonpath_tokens(expr: Text) -> List[Union[Text, int]]:
        """Parse minimal jsonpath syntax: $.data.items[0].id"""
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

    def _set_case_value_by_jsonpath(self, expr: Text, value: Any) -> None:
        tokens = self._parse_jsonpath_tokens(expr)
        container: Any = self.__yaml_case
        for token in tokens[:-1]:
            container = self._get_container_value(container, token)
        self._set_container_value(container, tokens[-1], value)

    def _dependent_type_for_sql(
        self,
        setup_sql: List,
        dependence_case_data: "DependentCaseData",
        jsonpath_dates: Dict,
    ) -> None:
        """Handle dependency values sourced from SQL setup."""
        if setup_sql is not None:
            if config.mysql_db.switch:
                setup_sql = ast.literal_eval(cache_regular(str(setup_sql)))
                sql_data = SetUpMySQL().setup_sql_data(sql=setup_sql)
                dependent_data = dependence_case_data.dependent_data
                for item in dependent_data:
                    dependency_jsonpath = item.jsonpath
                    extracted = self.jsonpath_data(obj=sql_data, expr=dependency_jsonpath)
                    cache_key = self.set_cache_value(item)
                    replace_key = self.replace_key(item)
                    replace_value = self.replace_value(item)

                    if cache_key is not None:
                        CacheHandler.update_cache(cache_name=cache_key, value=extracted[0])

                    if replace_key is not None:
                        final_replace_value = self._resolve_replace_value(replace_value, extracted)
                        jsonpath_dates[replace_key] = final_replace_value
                        self.url_replace(
                            replace_key=replace_key,
                            jsonpath_dates=jsonpath_dates,
                            replace_value=final_replace_value,
                        )
            else:
                WARNING.logger.warning("database switch is off, skip sql dependency handling")

    def dependent_handler(
        self,
        _jsonpath: Text,
        set_value: Text,
        replace_key: Text,
        replace_value: Any,
        jsonpath_dates: Dict,
        data: Dict,
        dependent_type: int,
    ) -> None:
        """Handle dependency extraction and replacement values."""
        extracted = self.jsonpath_data(data, _jsonpath)

        if set_value is not None:
            if len(extracted) > 1:
                CacheHandler.update_cache(cache_name=set_value, value=extracted)
            else:
                CacheHandler.update_cache(cache_name=set_value, value=extracted[0])

        if replace_key is not None:
            final_replace_value = self._resolve_replace_value(replace_value, extracted)
            if dependent_type == 0:
                jsonpath_dates[replace_key] = final_replace_value
            self.url_replace(
                replace_key=replace_key,
                jsonpath_dates=jsonpath_dates,
                replace_value=final_replace_value,
            )

    def is_dependent(self) -> Union[Dict, bool]:
        """Check and collect dependent replacement values."""
        dependent_type = self.__yaml_case.dependence_case
        dependence_case_data_list = self.__yaml_case.dependence_case_data
        setup_sql = self.__yaml_case.setup_sql

        if dependent_type is True:
            jsonpath_dates: Dict[Text, Any] = {}
            try:
                for dependence_case_data in dependence_case_data_list:
                    case_id = dependence_case_data.case_id
                    if case_id == "self":
                        self._dependent_type_for_sql(
                            setup_sql=setup_sql,
                            dependence_case_data=dependence_case_data,
                            jsonpath_dates=jsonpath_dates,
                        )
                    else:
                        re_data = regular(str(self.get_cache(case_id)))
                        re_data = ast.literal_eval(cache_regular(str(re_data)))
                        res = RequestControl(re_data).http_request()

                        if dependence_case_data.dependent_data is not None:
                            dependent_data = dependence_case_data.dependent_data
                            for item in dependent_data:
                                dependency_jsonpath = item.jsonpath
                                replace_key = self.replace_key(item)
                                replace_value = self.replace_value(item)
                                cache_key = self.set_cache_value(item)

                                if item.dependent_type == DependentType.RESPONSE.value:
                                    self.dependent_handler(
                                        data=json.loads(res.response_data),
                                        _jsonpath=dependency_jsonpath,
                                        set_value=cache_key,
                                        replace_key=replace_key,
                                        replace_value=replace_value,
                                        jsonpath_dates=jsonpath_dates,
                                        dependent_type=0,
                                    )
                                elif item.dependent_type == DependentType.REQUEST.value:
                                    self.dependent_handler(
                                        data=res.body,
                                        _jsonpath=dependency_jsonpath,
                                        set_value=cache_key,
                                        replace_key=replace_key,
                                        replace_value=replace_value,
                                        jsonpath_dates=jsonpath_dates,
                                        dependent_type=1,
                                    )
                                else:
                                    raise ValueError(
                                        "invalid dependent_type, supported: request/response/sql"
                                    )
                return jsonpath_dates
            except KeyError as exc:
                raise ValueNotFoundError(
                    f"dependence_case_data missing key: {exc}. please check yaml fields and indentation"
                ) from exc
            except TypeError as exc:
                raise ValueNotFoundError(
                    "dependence_case_data entries cannot be empty. please check yaml values and indentation"
                ) from exc

        return False

    def get_dependent_data(self) -> None:
        """Apply dependency replacement values to current yaml case object."""
        dependent_data = DependentCase(self.__yaml_case).is_dependent()
        if dependent_data is not None and dependent_data is not False:
            for key, value in dependent_data.items():
                try:
                    self._set_case_value_by_jsonpath(key, value)
                except Exception as exc:
                    raise ValueNotFoundError(
                        f"dependency replacement failed. jsonpath={key}, value={value}, error={exc}"
                    ) from exc
