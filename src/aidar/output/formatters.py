from __future__ import annotations

import json

from aidar.models.result import AggregateResult


def to_json(result: AggregateResult, indent: int = 2) -> str:
    return json.dumps(result.as_dict(), indent=indent)


def to_json_list(results: list[AggregateResult], indent: int = 2) -> str:
    return json.dumps([r.as_dict() for r in results], indent=indent)
