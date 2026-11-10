"""Teams, repository freeze, exit interviews, and voice tables (SQLModel)."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import Column, JSON, UniqueConstraint
from sqlmodel import Field, SQLModel


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid4())


class RepoIndexStatus(str, Enum):
    pending = "pending"
    running = "running"
    ready = "ready"
    failed = "failed"


class InterviewStatus(str, Enum):
    scheduled = "scheduled"
    consent = "consent"
    introductions = "introductions"
    student_turn = "student_turn"
    question = "question"
    response = "response"
    optional_probe = "optional_probe"
    evidence_recorded = "evidence_recorded"
    next_student = "next_student"
    closing = "closing"
    processing = "processing"
    lecturer_review = "lecturer_review"
    finalized = "finalized"
    paused = "paused"


class ConsentStatus(str, Enum):
    pending = "pending"
    granted = "granted"
    declined = "declined"


class ReviewStatus(str, Enum):
    pending = "pending"
    overridden = "overridden"
    finalized = "finalized"


class VoiceRoomStatus(str, Enum):
    idle = "idle"
    live = "live"
    ended = "ended"
    failed = "failed"


class VoiceRecordingStatus(str, Enum):
    none = "none"
    starting = "starting"
    recording = "recording"
    processing = "processing"
    ready = "ready"
    failed = "failed"


class Team(SQLModel, table=True):
    __tablename__ = "se_teams"

    id: str = Field(default_factory=_uuid, primary_key=True)
    name: str
    scenario_slug: Optional[str] = None
    scenario_version: Optional[str] = None
    # Real names for the exit interview (set in Admin → Teams).
    participant_names: Optional[list[str]] = Field(default=None, sa_column=Column(JSON))
    invite_code: str = Field(index=True, unique=True)
    created_at: datetime = Field(default_factory=_utc_now, index=True)


class TeamMember(SQLModel, table=True):
    __tablename__ = "se_team_members"
    __table_args__ = (UniqueConstraint("team_id", "user_id", name="uq_se_team_member"),)

    id: str = Field(default_factory=_uuid, primary_key=True)
    team_id: str = Field(foreign_key="se_teams.id", index=True)
    user_id: int = Field(index=True)
    joined_at: datetime = Field(default_factory=_utc_now)


class AuditEvent(SQLModel, table=True):
    __tablename__ = "se_audit_events"

    id: str = Field(default_factory=_uuid, primary_key=True)
    actor_id: Optional[int] = Field(default=None, index=True)
    action: str
    target_id: Optional[str] = None
    metadata_json: Optional[str] = None
    created_at: datetime = Field(default_factory=_utc_now)


class RepositorySubmission(SQLModel, table=True):
    __tablename__ = "se_repository_submissions"
    __table_args__ = (UniqueConstraint("team_id", "commit_sha", name="uq_se_team_commit"),)

    id: str = Field(default_factory=_uuid, primary_key=True)
    team_id: str = Field(foreign_key="se_teams.id", index=True)
    github_url: str
    owner: str
    repo: str
    branch: Optional[str] = None
    commit_sha: str = Field(index=True)
    frozen_at: datetime = Field(default_factory=_utc_now)
    index_status: str = Field(default=RepoIndexStatus.pending.value, index=True)
    index_error: Optional[str] = None
    index_json: Optional[dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    summary_json: Optional[dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    attempt_count: int = Field(default=0)
    updated_at: datetime = Field(default_factory=_utc_now)


class ExitInterviewSession(SQLModel, table=True):
    __tablename__ = "se_exit_interview_sessions"

    id: str = Field(default_factory=_uuid, primary_key=True)
    team_id: str = Field(foreign_key="se_teams.id", index=True)
    repository_submission_id: str = Field(foreign_key="se_repository_submissions.id")
    status: str = Field(default=InterviewStatus.scheduled.value, index=True)
    consent_status: str = Field(default=ConsentStatus.pending.value)
    target_duration_minutes: int = Field(default=30)
    current_participant_user_id: Optional[int] = Field(default=None, index=True)
    current_question_id: Optional[str] = None
    plan_json: Optional[dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    created_by_id: Optional[int] = None
    created_at: datetime = Field(default_factory=_utc_now, index=True)
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None


class InterviewParticipant(SQLModel, table=True):
    __tablename__ = "se_interview_participants"
    __table_args__ = (UniqueConstraint("session_id", "user_id", name="uq_se_interview_participant"),)

    id: str = Field(default_factory=_uuid, primary_key=True)
    session_id: str = Field(foreign_key="se_exit_interview_sessions.id", index=True)
    # Slot key for examiner turns/scoring. Shared-login sessions use negative
    # synthetic ids (-1, -2, …); display_name is the human label students type in.
    user_id: int = Field(index=True)
    display_name: str = Field(default="")
    joined_at: Optional[datetime] = None
    consent_status: str = Field(default=ConsentStatus.pending.value)
    turn_order: int = Field(default=0)


class InterviewQuestion(SQLModel, table=True):
    __tablename__ = "se_interview_questions"

    id: str = Field(default_factory=_uuid, primary_key=True)
    session_id: str = Field(foreign_key="se_exit_interview_sessions.id", index=True)
    target_user_id: int = Field(index=True)
    sequence: int = Field(default=0)
    competency: str
    difficulty: str = Field(default="medium")
    prompt: str
    code_refs: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    expected_concepts: list[Any] = Field(default_factory=list, sa_column=Column(JSON))
    rubric: str = Field(default="")
    follow_ups: list[Any] = Field(default_factory=list, sa_column=Column(JSON))
    hypothetical: bool = Field(default=False)
    status: str = Field(default="pending")


class InterviewAnswer(SQLModel, table=True):
    __tablename__ = "se_interview_answers"

    id: str = Field(default_factory=_uuid, primary_key=True)
    question_id: str = Field(foreign_key="se_interview_questions.id", index=True)
    user_id: int = Field(index=True)
    modality: str = Field(default="text")
    text: str
    is_probe: bool = Field(default=False)
    created_at: datetime = Field(default_factory=_utc_now)


class Assessment(SQLModel, table=True):
    __tablename__ = "se_assessments"
    __table_args__ = (UniqueConstraint("session_id", "user_id", name="uq_se_assessment_session_user"),)

    id: str = Field(default_factory=_uuid, primary_key=True)
    session_id: str = Field(foreign_key="se_exit_interview_sessions.id", index=True)
    user_id: int = Field(index=True)
    provisional_scores: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    evidence: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    review_status: str = Field(default=ReviewStatus.pending.value)
    reviewer_notes: Optional[str] = None
    reviewer_id: Optional[int] = None
    rubric_version: str = Field(default="m5-heuristic-v1")
    created_at: datetime = Field(default_factory=_utc_now)
    finalized_at: Optional[datetime] = None


class VoiceRoom(SQLModel, table=True):
    __tablename__ = "se_voice_rooms"
    __table_args__ = (UniqueConstraint("session_id", name="uq_se_voice_room_session"),)

    id: str = Field(default_factory=_uuid, primary_key=True)
    session_id: str = Field(foreign_key="se_exit_interview_sessions.id", index=True)
    room_name: str = Field(unique=True)
    status: str = Field(default=VoiceRoomStatus.idle.value)
    recording_status: str = Field(default=VoiceRecordingStatus.none.value)
    recording_indicator: bool = Field(default=False)
    egress_id: Optional[str] = None
    playback_url: Optional[str] = None
    local_file_path: Optional[str] = None
    created_at: datetime = Field(default_factory=_utc_now)
    ended_at: Optional[datetime] = None


class VoiceUtterance(SQLModel, table=True):
    __tablename__ = "se_voice_utterances"

    id: str = Field(default_factory=_uuid, primary_key=True)
    session_id: str = Field(foreign_key="se_exit_interview_sessions.id", index=True)
    user_id: int = Field(index=True)
    text: str
    is_final: bool = Field(default=True)
    corrected_text: Optional[str] = None
    track_sid: Optional[str] = None
    committed_answer_id: Optional[str] = Field(default=None, foreign_key="se_interview_answers.id")
    created_at: datetime = Field(default_factory=_utc_now)
