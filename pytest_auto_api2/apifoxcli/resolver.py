from __future__ import annotations

import re
from typing import Any

from .context import RunContext

TOKEN_RE = re.compile(r"\$\{([^}]+)\}")


def _resolve_token(token: str, context: RunContext) -> Any:
    if token.startswith("env."):
        key = token.split(".", 1)[1]
        return context.env.get("variables", {}).get(key, context.env.get(key))
    if token.startswith("dataset."):
        key = token.split(".", 1)[1]
        return context.dataset.get(key)
    if token.startswith("context."):
        key = token.split(".", 1)[1]
        return context.values.get(key)
    raise KeyError(f"unsupported token: {token}")


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
            had_missing_token = True
            return ""
        return str(resolved)

    resolved_value = TOKEN_RE.sub(replace, value)
    if missing == "none" and had_token and had_missing_token:
        return None
    return resolved_value
