from __future__ import annotations

from jsonpath import jsonpath


def apply_extractors(extractors, response, context) -> None:
    payload = response.json()
    for extractor in extractors:
        result = jsonpath(payload, extractor.expr)
        if result is False:
            raise AssertionError(f"extract failed: {extractor.expr}")
        context.values[extractor.name] = result[0] if len(result) == 1 else result
