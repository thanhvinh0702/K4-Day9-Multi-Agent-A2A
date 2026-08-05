from __future__ import annotations

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable, TypeVar


T = TypeVar("T")
TWO_PLACES = Decimal("0.01")


def unique(values: Iterable[T]) -> list[T]:
    """Return values in first-seen order."""
    seen: set[T] = set()
    result: list[T] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def money(value: Decimal) -> float:
    return float(value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP))


def hours_between(later: str, earlier: str) -> float | None:
    if not later or not earlier:
        return None
    delta = datetime.fromisoformat(later) - datetime.fromisoformat(earlier)
    value = Decimal(str(delta.total_seconds())) / Decimal("3600")
    return float(value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP))


def is_after(later: str | None, earlier: str | None) -> bool:
    """Compare raw timestamps; classification must not depend on rounded hours."""
    if not later or not earlier:
        return False
    return datetime.fromisoformat(later) > datetime.fromisoformat(earlier)
