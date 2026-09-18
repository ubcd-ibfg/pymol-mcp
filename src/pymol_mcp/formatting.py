"""Small shared helpers for tool output: pagination and truncation so a
large structure's atom list or coordinate set doesn't flood the agent's
context window.
"""

from __future__ import annotations

from typing import Any, TypedDict

DEFAULT_ITERATE_LIMIT = 500
MAX_ITERATE_LIMIT = 5000


class Page(TypedDict):
    items: list[Any]
    total: int
    offset: int
    count: int
    has_more: bool


def paginate(items: list[Any], offset: int, limit: int) -> Page:
    total = len(items)
    window = items[offset : offset + limit]
    return {
        "items": window,
        "total": total,
        "offset": offset,
        "count": len(window),
        "has_more": offset + len(window) < total,
    }


def clamp_limit(limit: int, default: int = DEFAULT_ITERATE_LIMIT, maximum: int = MAX_ITERATE_LIMIT) -> int:
    if limit <= 0:
        return default
    return min(limit, maximum)
