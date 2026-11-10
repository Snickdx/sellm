"""Lightweight versioned schema marker (replaces ad-hoc ALTER sprawl over time)."""

from __future__ import annotations

from sqlalchemy import text
from sqlmodel import Session, SQLModel, Field


class SchemaVersion(SQLModel, table=True):
    id: int = Field(default=1, primary_key=True)
    version: int = Field(default=0)


CURRENT_SCHEMA_VERSION = 2  # M2: authsession.expires_at + argon2 password hashes


def ensure_schema_version(engine) -> int:
    """Ensure SchemaVersion row exists and return current stored version."""
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        row = session.get(SchemaVersion, 1)
        if row is None:
            row = SchemaVersion(id=1, version=CURRENT_SCHEMA_VERSION)
            session.add(row)
            session.commit()
            return CURRENT_SCHEMA_VERSION
        if row.version < CURRENT_SCHEMA_VERSION:
            row.version = CURRENT_SCHEMA_VERSION
            session.add(row)
            session.commit()
        return int(row.version)
