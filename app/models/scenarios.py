"""SQLModel tables for imported YAML scenarios."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import Column, JSON, UniqueConstraint
from sqlmodel import Field, SQLModel


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ScenarioRecordStatus(str, Enum):
    pending_source = "PENDING_SOURCE"
    draft = "draft"
    approved = "approved"
    retired = "retired"


class MessageRole(str, Enum):
    student = "student"
    persona = "persona"
    system = "system"


class Scenario(SQLModel, table=True):
    __tablename__ = "scenarios"
    __table_args__ = (UniqueConstraint("slug", "version", name="uq_scenario_slug_version"),)

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    slug: str = Field(index=True)
    version: str
    title: str
    status: str = Field(default=ScenarioRecordStatus.draft.value, index=True)
    brief: str = Field(default="")
    source_manifest: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    gaps_json: Optional[dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    evaluation_json: Optional[dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    source_path: Optional[str] = None
    created_at: datetime = Field(default_factory=_utc_now, index=True)


class ScenarioPersona(SQLModel, table=True):
    __tablename__ = "scenario_personas"
    __table_args__ = (UniqueConstraint("scenario_id", "persona_key", name="uq_scenario_persona"),)

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    scenario_id: str = Field(foreign_key="scenarios.id", index=True)
    persona_key: str
    config: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))


class ScenarioFact(SQLModel, table=True):
    __tablename__ = "scenario_facts"
    __table_args__ = (UniqueConstraint("scenario_id", "fact_key", name="uq_scenario_fact"),)

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    scenario_id: str = Field(foreign_key="scenarios.id", index=True)
    fact_key: str
    text: str
    provenance: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    source_ref: list[Any] = Field(default_factory=list, sa_column=Column(JSON))
    known_by: list[Any] = Field(default_factory=list, sa_column=Column(JSON))
    disclosure: str = Field(default="when_relevant")
    status: str
    origin: str
