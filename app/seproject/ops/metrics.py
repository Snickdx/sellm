"""Simple in-process counters for voice/recording failures."""

from __future__ import annotations

_counters: dict[str, int] = {}


def incr(name: str, amount: int = 1) -> None:
    _counters[name] = _counters.get(name, 0) + amount


def get(name: str) -> int:
    return _counters.get(name, 0)
