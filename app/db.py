"""Shared SQLModel session bound to sellm conversation DB."""

from __future__ import annotations

from collections.abc import Generator
from typing import TYPE_CHECKING

from sqlmodel import Session

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

_engine: Engine | None = None


def configure_engine(engine: Engine) -> None:
    global _engine
    _engine = engine


def get_engine() -> Engine:
    if _engine is None:
        raise RuntimeError("DB engine not configured — call configure_engine first")
    return _engine


def get_db() -> Generator[Session, None, None]:
    with Session(get_engine()) as session:
        yield session
