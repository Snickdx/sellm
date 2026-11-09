"""Text-based exit interview orchestration and provisional assessment."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.seproject.db import get_db
from app.seproject.deps import AuthUser, ensure_team_access, get_current_user, require_instructor
from app.seproject.examiner.competencies import RUBRIC_VERSION
from app.seproject.examiner.planner import generate_question_plan
from app.seproject.examiner.scorer import score_session
from app.seproject.examiner.state import (
    SessionBundle,
    advance_to_question,
    after_evidence,
    all_participants_consented,
    begin_processing,
    finalize_session,
    load_session,
    mark_lecturer_review,
    next_participant_with_work,
    optional_probe,
    ordered_participants,
    pending_questions_for,
    record_response,
    start_session,
    unanswered_question_ids,
)
from app.seproject.exit_models import (
    Assessment,
    AuditEvent,
    ConsentStatus,
    ExitInterviewSession,
    InterviewAnswer,
    InterviewParticipant,
    InterviewQuestion,
    InterviewStatus,
    RepoIndexStatus,
    RepositorySubmission,
    ReviewStatus,
    Team,
    TeamMember,
)

router = APIRouter(tags=["exit-interviews"])


class CreateExitSessionRequest(BaseModel):
    repository_submission_id: str
    participant_user_ids: list[int] = Field(min_length=1)
    target_duration_minutes: int = Field(default=30, ge=10, le=120)
    questions_per_student: int = Field(default=5, ge=1, le=5)


class ConsentRequest(BaseModel):
    granted: bool = True


class AnswerRequest(BaseModel):
    text: str = Field(min_length=1, max_length=8000)
    request_probe: bool = False


class ReviewRequest(BaseModel):
    finalize: bool = False
    reviewer_notes: str | None = None
    override_scores: dict | None = None


def _team_access(db: Session, team_id: str, user: AuthUser) -> Team:
    return ensure_team_access(db, team_id, user)


def _session_access(db: Session, session_id: str, user: AuthUser) -> SessionBundle:
    bundle = load_session(db, session_id)
    if bundle is None:
        raise HTTPException(status_code=404, detail="Exit session not found")
    _team_access(db, bundle.session.team_id, user)
    return bundle


def _serialize_question(q: InterviewQuestion) -> dict:
    return {
        "id": str(q.id),
        "sequence": q.sequence,
        "target_user_id": q.target_user_id,
        "competency": q.competency,
        "difficulty": q.difficulty,
        "prompt": q.prompt,
        "code_refs": q.code_refs,
        "expected_concepts": q.expected_concepts,
        "rubric": q.rubric,
        "follow_ups": q.follow_ups,
        "hypothetical": q.hypothetical,
        "status": q.status,
        "answers": [],
    }


def _serialize_question_with_answers(q: InterviewQuestion, answers: list) -> dict:
    payload = _serialize_question(q)
    payload["answers"] = [
        {
            "id": str(a.id),
            "user_id": a.user_id,
            "text": a.text,
            "is_probe": a.is_probe,
            "modality": a.modality,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in answers
    ]
    return payload


def _serialize_session(bundle: SessionBundle) -> dict:
    session = bundle.session
    return {
        "id": str(session.id),
        "team_id": str(session.team_id),
        "repository_submission_id": str(session.repository_submission_id),
        "status": session.status,
        "consent_status": session.consent_status,
        "target_duration_minutes": session.target_duration_minutes,
        "current_participant_user_id": session.current_participant_user_id,
        "current_question_id": session.current_question_id,
        "plan": session.plan_json,
        "started_at": session.started_at.isoformat() if session.started_at else None,
        "ended_at": session.ended_at.isoformat() if session.ended_at else None,
        "participants": [
            {
                "user_id": p.user_id,
                "display_name": (
                    bundle.users_by_id[p.user_id].username
                    if p.user_id in bundle.users_by_id
                    else str(p.user_id)
                ),
                "consent_status": p.consent_status,
                "turn_order": p.turn_order,
            }
            for p in ordered_participants(bundle.participants)
        ],
        "questions": [
            _serialize_question_with_answers(q, bundle.answers_for(q.id))
            for q in sorted(bundle.questions, key=lambda x: x.sequence)
        ],
        "unanswered_question_ids": unanswered_question_ids(bundle.questions),
    }


@router.post("/admin/teams/{team_id}/exit-session", status_code=201)
@router.post("/teams/{team_id}/exit-session", status_code=201)
def create_exit_session(
    team_id: str,
    body: CreateExitSessionRequest,
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    team = _team_access(db, team_id, user)
    repo = db.get(RepositorySubmission, body.repository_submission_id)
    if repo is None or repo.team_id != team.id:
        raise HTTPException(status_code=400, detail="Repository submission not found for team")
    if repo.index_status != RepoIndexStatus.ready.value or not repo.index_json:
        raise HTTPException(status_code=400, detail="Repository index is not ready")

    member_ids = {
        m.user_id for m in db.exec(select(TeamMember).where(TeamMember.team_id == team.id)).all()
    }
    for uid in body.participant_user_ids:
        if uid not in member_ids:
            raise HTTPException(status_code=400, detail=f"User {uid} is not on the team")

    plan = generate_question_plan(
        participant_user_ids=body.participant_user_ids,
        index=repo.index_json,
        questions_per_student=body.questions_per_student,
    )

    session = ExitInterviewSession(
        team_id=team.id,
        repository_submission_id=repo.id,
        status=InterviewStatus.scheduled.value,
        consent_status=ConsentStatus.pending.value,
        target_duration_minutes=body.target_duration_minutes,
        plan_json=plan,
        created_by_id=user.id,
    )
    db.add(session)
    db.flush()

    for order, uid in enumerate(body.participant_user_ids):
        db.add(
            InterviewParticipant(
                session_id=session.id,
                user_id=uid,
                turn_order=order,
                consent_status=ConsentStatus.pending.value,
            )
        )

    for q in plan["questions"]:
        db.add(
            InterviewQuestion(
                session_id=session.id,
                target_user_id=int(q["target_user_id"]),
                sequence=q["sequence"],
                competency=q["competency"],
                difficulty=q["difficulty"],
                prompt=q["prompt"],
                code_refs=q["code_refs"],
                expected_concepts=q["expected_concepts"],
                rubric=q["rubric"],
                follow_ups=q["follow_ups"],
                hypothetical=bool(q.get("hypothetical")),
                status="pending",
            )
        )

    db.add(
        AuditEvent(
            actor_id=user.id,
            action="exit_session.create",
            target_id=str(session.id),
            metadata_json=None,
        )
    )
    db.commit()
    bundle = load_session(db, session.id)
    assert bundle is not None
    return _serialize_session(bundle)


@router.get("/exit-sessions/{session_id}")
def get_exit_session(
    session_id: str,
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return _serialize_session(_session_access(db, session_id, user))


@router.get("/teams/{team_id}/exit-sessions")
def list_team_exit_sessions(
    team_id: str,
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    _team_access(db, team_id, user)
    rows = list(
        db.exec(
            select(ExitInterviewSession)
            .where(ExitInterviewSession.team_id == team_id)
            .order_by(ExitInterviewSession.created_at.desc())
        ).all()
    )
    return [
        {
            "id": str(r.id),
            "status": r.status,
            "consent_status": r.consent_status,
            "repository_submission_id": str(r.repository_submission_id),
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@router.post("/exit-sessions/{session_id}/consent")
def consent(
    session_id: str,
    body: ConsentRequest,
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    bundle = _session_access(db, session_id, user)
    session = bundle.session
    participant = next((p for p in bundle.participants if p.user_id == user.id), None)
    if participant is None and not user.is_instructor:
        raise HTTPException(status_code=403, detail="Not a session participant")
    if participant is not None:
        participant.consent_status = (
            ConsentStatus.granted.value if body.granted else ConsentStatus.declined.value
        )
        participant.joined_at = datetime.now(timezone.utc)
    if all_participants_consented(bundle.participants):
        session.consent_status = ConsentStatus.granted.value
        if session.status in {InterviewStatus.scheduled.value, InterviewStatus.consent.value}:
            session.status = InterviewStatus.consent.value
    elif any(p.consent_status == ConsentStatus.declined.value for p in bundle.participants):
        session.consent_status = ConsentStatus.declined.value
    else:
        session.consent_status = ConsentStatus.pending.value
        session.status = InterviewStatus.consent.value
    db.commit()
    return _serialize_session(load_session(db, session_id))  # type: ignore[arg-type]


@router.post("/exit-sessions/{session_id}/start")
def start_exit_session(
    session_id: str,
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    bundle = _session_access(db, session_id, user)
    if not user.is_instructor and user.id not in {p.user_id for p in bundle.participants}:
        raise HTTPException(status_code=403, detail="Not allowed to start")
    try:
        start_session(bundle)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if (
        bundle.session.status == InterviewStatus.student_turn.value
        and bundle.session.current_participant_user_id
    ):
        pending = pending_questions_for(bundle.questions, bundle.session.current_participant_user_id)
        if pending:
            advance_to_question(bundle.session, pending[0])
    db.commit()
    return _serialize_session(load_session(db, session_id))  # type: ignore[arg-type]


@router.post("/exit-sessions/{session_id}/next")
def next_question(
    session_id: str,
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    bundle = _session_access(db, session_id, user)
    session = bundle.session
    if session.status == InterviewStatus.paused.value:
        raise HTTPException(status_code=409, detail="Session is paused — resume first")
    if session.status in {
        InterviewStatus.closing.value,
        InterviewStatus.processing.value,
        InterviewStatus.lecturer_review.value,
        InterviewStatus.finalized.value,
    }:
        raise HTTPException(status_code=400, detail="Interview is finished")

    if session.status in {
        InterviewStatus.student_turn.value,
        InterviewStatus.next_student.value,
        InterviewStatus.evidence_recorded.value,
    }:
        if session.current_participant_user_id is None:
            nxt = next_participant_with_work(bundle.participants, bundle.questions)
            if nxt is None:
                session.status = InterviewStatus.closing.value
                db.commit()
                return _serialize_session(load_session(db, session_id))  # type: ignore[arg-type]
            session.current_participant_user_id = nxt.user_id
        pending = pending_questions_for(bundle.questions, session.current_participant_user_id)
        if not pending:
            after_evidence(bundle)
            db.commit()
            return _serialize_session(load_session(db, session_id))  # type: ignore[arg-type]
        advance_to_question(session, pending[0])
        db.commit()
        return _serialize_session(load_session(db, session_id))  # type: ignore[arg-type]

    raise HTTPException(status_code=400, detail=f"Cannot advance from status={session.status}")


@router.post("/exit-sessions/{session_id}/answers")
def submit_answer(
    session_id: str,
    body: AnswerRequest,
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    bundle = _session_access(db, session_id, user)
    session = bundle.session
    if session.current_question_id is None:
        raise HTTPException(status_code=400, detail="No active question")
    question = db.get(InterviewQuestion, session.current_question_id)
    if question is None:
        raise HTTPException(status_code=404, detail="Question not found")
    if question.target_user_id != user.id:
        raise HTTPException(status_code=403, detail="Only the target student may answer")

    answer = InterviewAnswer(
        question_id=question.id,
        user_id=user.id,
        modality="text",
        text=body.text.strip(),
        is_probe=False,
    )
    db.add(answer)
    record_response(session, question)

    probe_prompt = None
    if body.request_probe and question.follow_ups:
        optional_probe(session, question)
        probe_prompt = question.follow_ups[0]
    else:
        # refresh question list statuses in bundle
        for q in bundle.questions:
            if q.id == question.id:
                q.status = question.status
        after_evidence(bundle)
        if session.status == InterviewStatus.student_turn.value and session.current_participant_user_id:
            pending = pending_questions_for(bundle.questions, session.current_participant_user_id)
            if pending:
                advance_to_question(session, pending[0])

    db.commit()
    payload = _serialize_session(load_session(db, session_id))  # type: ignore[arg-type]
    payload["probe_prompt"] = probe_prompt
    return payload


@router.post("/exit-sessions/{session_id}/answers/probe")
def submit_probe_answer(
    session_id: str,
    body: AnswerRequest,
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    bundle = _session_access(db, session_id, user)
    session = bundle.session
    if session.status != InterviewStatus.optional_probe.value or session.current_question_id is None:
        raise HTTPException(status_code=400, detail="No active probe")
    question = db.get(InterviewQuestion, session.current_question_id)
    if question is None or question.target_user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your probe")
    db.add(
        InterviewAnswer(
            question_id=question.id,
            user_id=user.id,
            modality="text",
            text=body.text.strip(),
            is_probe=True,
        )
    )
    for q in bundle.questions:
        if q.id == question.id:
            q.status = question.status
    after_evidence(bundle)
    if session.status == InterviewStatus.student_turn.value and session.current_participant_user_id:
        pending = pending_questions_for(bundle.questions, session.current_participant_user_id)
        if pending:
            advance_to_question(session, pending[0])
    db.commit()
    return _serialize_session(load_session(db, session_id))  # type: ignore[arg-type]


@router.post("/exit-sessions/{session_id}/pause")
def pause_session(
    session_id: str,
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    bundle = _session_access(db, session_id, user)
    session = bundle.session
    if session.status == InterviewStatus.paused.value:
        return _serialize_session(bundle)
    session.plan_json = {**(session.plan_json or {}), "_paused_from": session.status}
    session.status = InterviewStatus.paused.value
    db.commit()
    return _serialize_session(load_session(db, session_id))  # type: ignore[arg-type]


@router.post("/exit-sessions/{session_id}/resume")
def resume_session(
    session_id: str,
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    bundle = _session_access(db, session_id, user)
    session = bundle.session
    if session.status != InterviewStatus.paused.value:
        return _serialize_session(bundle)
    prev = (session.plan_json or {}).get("_paused_from", InterviewStatus.student_turn.value)
    session.status = str(prev)
    db.commit()
    return _serialize_session(load_session(db, session_id))  # type: ignore[arg-type]


@router.post("/exit-sessions/{session_id}/finish")
def finish_session(
    session_id: str,
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    bundle = _session_access(db, session_id, user)
    begin_processing(bundle.session)
    db.commit()

    bundle = load_session(db, session_id)
    assert bundle is not None
    repo = db.get(RepositorySubmission, bundle.session.repository_submission_id)
    sha = repo.commit_sha if repo else ""
    reports = score_session(bundle, sha)

    for old in db.exec(select(Assessment).where(Assessment.session_id == bundle.session.id)).all():
        db.delete(old)
    for report in reports:
        db.add(
            Assessment(
                session_id=bundle.session.id,
                user_id=int(report["student_id"]),
                provisional_scores={"competencies": report["competencies"], "provisional": True},
                evidence={
                    "coverage_warnings": report["coverage_warnings"],
                    "repository_sha": report["repository_sha"],
                },
                review_status=ReviewStatus.pending.value,
                rubric_version=RUBRIC_VERSION,
            )
        )
    mark_lecturer_review(bundle.session)
    db.add(
        AuditEvent(
            actor_id=user.id,
            action="exit_session.finish",
            target_id=str(bundle.session.id),
            metadata_json=None,
        )
    )
    db.commit()
    return {
        "session": _serialize_session(load_session(db, session_id)),  # type: ignore[arg-type]
        "reports": reports,
    }


@router.get("/admin/exit-sessions/{session_id}/report")
@router.get("/exit-sessions/{session_id}/report")
def get_report(
    session_id: str,
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    bundle = _session_access(db, session_id, user)
    repo = db.get(RepositorySubmission, bundle.session.repository_submission_id)
    return {
        "session_id": str(bundle.session.id),
        "status": bundle.session.status,
        "repository_sha": repo.commit_sha if repo else None,
        "assessments": [
            {
                "id": str(a.id),
                "student_id": a.user_id,
                "provisional": a.review_status != ReviewStatus.finalized.value,
                "review_status": a.review_status,
                "provisional_scores": a.provisional_scores,
                "evidence": a.evidence,
                "reviewer_notes": a.reviewer_notes,
                "rubric_version": a.rubric_version,
                "finalized_at": a.finalized_at.isoformat() if a.finalized_at else None,
            }
            for a in bundle.assessments
        ],
        "unanswered_question_ids": unanswered_question_ids(bundle.questions),
    }


@router.post("/admin/assessments/{assessment_id}/review")
def review_assessment(
    assessment_id: str,
    body: ReviewRequest,
    instructor: AuthUser = Depends(require_instructor),
    db: Session = Depends(get_db),
) -> dict:
    assessment = db.get(Assessment, assessment_id)
    if assessment is None:
        raise HTTPException(status_code=404, detail="Assessment not found")
    if body.override_scores is not None:
        assessment.provisional_scores = {
            **(assessment.provisional_scores or {}),
            "override": body.override_scores,
            "provisional": not body.finalize,
        }
        assessment.review_status = ReviewStatus.overridden.value
    if body.reviewer_notes is not None:
        assessment.reviewer_notes = body.reviewer_notes
    assessment.reviewer_id = instructor.id
    if body.finalize:
        assessment.review_status = ReviewStatus.finalized.value
        assessment.finalized_at = datetime.now(timezone.utc)
        bundle = load_session(db, assessment.session_id)
        if bundle and all(a.review_status == ReviewStatus.finalized.value for a in bundle.assessments):
            # also update the one we just changed in memory
            finalize_session(bundle.session)
    db.add(
        AuditEvent(
            actor_id=instructor.id,
            action="assessment.review",
            target_id=str(assessment.id),
            metadata_json=None,
        )
    )
    db.commit()
    db.refresh(assessment)
    return {
        "id": str(assessment.id),
        "review_status": assessment.review_status,
        "provisional_scores": assessment.provisional_scores,
        "reviewer_notes": assessment.reviewer_notes,
        "finalized_at": assessment.finalized_at.isoformat() if assessment.finalized_at else None,
    }
