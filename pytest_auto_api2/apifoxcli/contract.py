from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from .resolver import resolve_value


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


def build_case_request(case, api, context) -> PreparedRequest:
    request_contract = ((api.spec.contract or {}).get("request") or {})
    case_request = case.spec.request or {}
    method = request_contract.get("method")
    path = request_contract.get("path")
    missing_fields = [name for name, value in (("method", method), ("path", path)) if not value]
    if missing_fields:
        missing = ", ".join(missing_fields)
        raise ValueError(
            f"missing contract request {missing} for case '{case.id}' and api '{api.id}'"
        )

    headers = dict(context.env.get("headers") or {})
    headers.update(case_request.get("headers") or {})

    return PreparedRequest(
        method=method,
        path=path,
        headers=resolve_value(headers, context, missing="none"),
        query=resolve_value(case_request.get("query"), context) if case_request.get("query") else None,
        json_body=resolve_value(case_request.get("json"), context) if case_request.get("json") else None,
        form=resolve_value(case_request.get("form"), context) if case_request.get("form") else None,
    )
