from __future__ import annotations

import re
from typing import Any, Iterable

from .context import RunContext

TOKEN_RE = re.compile(r"\$\{\{([^{}]+)\}\}")
LEGACY_TOKEN_RE = re.compile(r"\$\{(?!\{)([^{}]+)\}")


def _resolve_token(token: str, context: RunContext) -> Any:
    if token in context.values:
        return context.values[token]
    if token in context.dataset:
        return context.dataset[token]
    return context.env.get("variables", {}).get(token)


def resolve_value(value: Any, context: RunContext, missing: str = "empty") -> Any:
    if isinstance(value, dict):
        return {key: resolve_value(item, context, missing=missing) for key, item in value.items()}
    if isinstance(value, list):
        return [resolve_value(item, context, missing=missing) for item in value]
    if not isinstance(value, str):
        return value

    had_token = False
    had_missing_token = False

    def replace(match: re.Match[str]) -> str:
        nonlocal had_token, had_missing_token
        token = match.group(1)
        had_token = True
        resolved = _resolve_token(token, context)
        if resolved is None:
            if missing == "error":
                raise KeyError(f"missing token: {token}")
            had_missing_token = True
            return ""
        return str(resolved)

    resolved_value = TOKEN_RE.sub(replace, value)
    if missing == "none" and had_token and had_missing_token:
        return None
    return resolved_value


def iter_expression_tokens(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield from TOKEN_RE.findall(value)
        return
    if isinstance(value, dict):
        for item in value.values():
            yield from iter_expression_tokens(item)
        return
    if isinstance(value, list):
        for item in value:
            yield from iter_expression_tokens(item)


def iter_legacy_expression_tokens(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield from LEGACY_TOKEN_RE.findall(value)
        return
    if isinstance(value, dict):
        for item in value.values():
            yield from iter_legacy_expression_tokens(item)
        return
    if isinstance(value, list):
        for item in value:
            yield from iter_legacy_expression_tokens(item)
