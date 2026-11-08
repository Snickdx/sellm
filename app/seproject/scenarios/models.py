"""Pydantic models for on-disk scenario packages."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class FactStatus(str, Enum):
    confirmed = "confirmed"
    clarified = "clarified"
    assumed = "assumed"
    unresolved = "unresolved"
    conflicting = "conflicting"


class FactOrigin(str, Enum):
    transcript = "transcript"
    instructor = "instructor"


class Disclosure(str, Enum):
    when_relevant = "when_relevant"
    when_asked = "when_asked"
    never_student = "never_student"


class GapPriority(str, Enum):
    critical = "critical"
    important = "important"
    optional = "optional"


class GapAction(str, Enum):
    accept = "accept"
    modify = "modify"
    reject = "reject"
    defer = "defer"


class ScenarioStatus(str, Enum):
    pending_source = "PENDING_SOURCE"
    draft = "draft"
    approved = "approved"
    retired = "retired"


class SourceRef(BaseModel):
    file: str
    cue_id: str
    start: str | None = None
    end: str | None = None
    speaker: str | None = None
    note: str | None = None


class KnowledgeFact(BaseModel):
    id: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    category: str = Field(min_length=1)
    status: FactStatus
    origin: FactOrigin
    source_refs: list[SourceRef] = Field(default_factory=list)
    known_by: list[str] = Field(default_factory=list)
    disclosure: Disclosure = Disclosure.when_relevant
    acceptance_criteria: list[str] = Field(default_factory=list)
    decision_id: str | None = None
    approved_by: str | None = None
    approved_at: str | None = None
    rationale: str | None = None

    @model_validator(mode="after")
    def check_provenance(self) -> KnowledgeFact:
        if self.status == FactStatus.confirmed and self.origin == FactOrigin.transcript:
            if not self.source_refs:
                raise ValueError(f"{self.id}: confirmed transcript facts require source_refs")
        if self.status == FactStatus.assumed:
            missing = [
                name
                for name, value in [
                    ("decision_id", self.decision_id),
                    ("approved_by", self.approved_by),
                    ("approved_at", self.approved_at),
                    ("rationale", self.rationale),
                ]
                if not value
            ]
            if missing:
                raise ValueError(f"{self.id}: assumed facts require {', '.join(missing)}")
        return self


class Persona(BaseModel):
    id: str
    display_name: str
    role: str
    priorities: list[str] = Field(default_factory=list)
    communication_style: str = ""
    known_fact_ids: list[str] = Field(default_factory=list)
    uncertainty_policy: str = "Admit when unsure; do not invent policy."
    referral_rules: list[str] = Field(default_factory=list)


class GapQuestion(BaseModel):
    id: str
    priority: GapPriority
    prompt: str
    citations: list[SourceRef] = Field(default_factory=list)
    why_it_matters: str = ""
    alternatives: list[str] = Field(default_factory=list)
    recommended_default: str | None = None
    status: str = "open"  # open | decided


class GapDecision(BaseModel):
    decision_id: str
    gap_id: str
    action: GapAction
    chosen: str | None = None
    modified_text: str | None = None
    rationale: str = ""
    approved_by: str
    approved_at: str
    resulting_fact_ids: list[str] = Field(default_factory=list)


class GapsFile(BaseModel):
    open_questions: list[GapQuestion] = Field(default_factory=list)
    decisions: list[GapDecision] = Field(default_factory=list)


class EvaluationFile(BaseModel):
    """Instructor-only oracle. Never expose via student APIs."""

    version: str = "1"
    hidden_checks: list[dict[str, Any]] = Field(default_factory=list)
    notes: str = ""


class ScenarioMeta(BaseModel):
    slug: str
    title: str
    version: str
    status: ScenarioStatus
    brief: str
    source_status: str = "unknown"
    source_notes: str = ""
    approved_by: str | None = None
    approved_at: str | None = None

    @field_validator("slug")
    @classmethod
    def slug_format(cls, value: str) -> str:
        if not value or any(ch.isspace() for ch in value):
            raise ValueError("slug must be non-empty without whitespace")
        return value


class ScenarioPackage(BaseModel):
    meta: ScenarioMeta
    personas: list[Persona] = Field(default_factory=list)
    facts: list[KnowledgeFact] = Field(default_factory=list)
    gaps: GapsFile | None = None
    evaluation: EvaluationFile | None = None
    cue_ids_by_file: dict[str, set[str]] = Field(default_factory=dict)

    model_config = {"arbitrary_types_allowed": True}
