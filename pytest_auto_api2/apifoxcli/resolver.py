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


def resolve_value(value: Any, context: RunContext) -> Any:
    if isinstance(value, dict):
        return {key: resolve_value(item, context) for key, item in value.items()}
    if isinstance(value, list):
        return [resolve_value(item, context) for item in value]
    if not isinstance(value, str):
        return value

    def replace(match: re.Match[str]) -> str:
        token = match.group(1)
        resolved = _resolve_token(token, context)
        return "" if resolved is None else str(resolved)

    return TOKEN_RE.sub(replace, value)
