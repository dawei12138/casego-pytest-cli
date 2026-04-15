from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Dict, List, Optional

from .resolver import resolve_value


PATH_PARAM_RE = re.compile(r"(?<!\$)\{([^{}]+)\}(?!\})")


@dataclass
class PreparedRequest:
    method: str
    path: str
    headers: Dict[str, str]
    query: Optional[Dict[str, object]]
    json_body: Optional[Dict[str, object]]
    form: Optional[Dict[str, object]]


def validate_case_contract(case, api) -> List[str]:
    errors: List[str] = []
    request_contract = ((api.spec.contract or {}).get("request") or {})
    form_schema = request_contract.get("formSchema") or {}
    provided_form = ((case.spec.request or {}).get("form") or {})
    for field_name, field_spec in form_schema.items():
        if field_spec.get("required") and field_name not in provided_form:
            errors.append(f"missing required form field: {field_name}")
    return errors


def _contract_path_to_snapshot(path: str) -> str:
    return PATH_PARAM_RE.sub(lambda match: f"${{{{{match.group(1)}}}}}", path)


def build_case_request(case, api, context) -> PreparedRequest:
    request_contract = ((api.spec.contract or {}).get("request") or {})
    request_snapshot = api.spec.request
    case_request = case.spec.request or {}
    method = request_snapshot.method if request_snapshot and request_snapshot.method else request_contract.get("method")
    path = request_snapshot.path if request_snapshot and request_snapshot.path else request_contract.get("path")
    missing_fields = [name for name, value in (("method", method), ("path", path)) if not value]
    if missing_fields:
        missing = ", ".join(missing_fields)
        raise ValueError(
            f"missing contract request {missing} for case '{case.id}' and api '{api.id}'"
        )
    if not request_snapshot:
        path = _contract_path_to_snapshot(str(path))

    headers = dict(context.env.get("headers") or {})
    headers.update(case_request.get("headers") or {})

    return PreparedRequest(
        method=str(method),
        path=resolve_value(path, context, missing="error"),
        headers=resolve_value(headers, context, missing="none"),
        query=resolve_value(case_request.get("query"), context) if case_request.get("query") else None,
        json_body=resolve_value(case_request.get("json"), context) if case_request.get("json") else None,
        form=resolve_value(case_request.get("form"), context) if case_request.get("form") else None,
    )
