"""Text-based exit interview orchestration and provisional assessment."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.course.db import get_db
from app.course.deps import AuthUser, ensure_team_access, get_current_user, require_instructor
from app.course.examiner.competencies import RUBRIC_VERSION
from app.course.examiner.planner import generate_question_plan
from app.course.examiner.scorer import score_session
from app.course.examiner.state import (
    SessionBundle,
    advance_to_question,
    after_evidence,
    begin_processing,
    finalize_session,
    load_session,
    mark_lecturer_review,
    next_participant_with_work,
    optional_probe,
    ordered_participants,
    pending_questions_for,
    record_response,
    spawn_skip_alternate,
    start_session,
    unanswered_question_ids,
)
from app.models.exit import (
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
    VoiceRoom,
    VoiceUtterance,
)

router = APIRouter(tags=["exit-interviews"])


class CreateExitSessionRequest(BaseModel):
    # Optional — defaults to the team's latest ready repository from Admin → Teams.
    repository_submission_id: str | None = None
    # Optional — defaults to participant_names configured on the team in Admin.
    participant_names: list[str] = Field(default_factory=list)
    target_duration_minutes: int = Field(default=30, ge=10, le=120)
    questions_per_student: int = Field(default=5, ge=1, le=5)


def _normalize_participant_names(names: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in names:
        name = " ".join(str(raw).split()).strip()
        if not name:
            continue
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(name)
    if not cleaned:
        raise HTTPException(status_code=400, detail="Provide at least one participant name")
    return cleaned


def _slot_user_id(order: int) -> int:
    """Synthetic participant key (negative) so shared-login sessions need no user rows."""
    return -(order + 1)


def _participant_label(bundle: SessionBundle, slot_user_id: int) -> str:
    for p in bundle.participants:
        if p.user_id == slot_user_id:
            if p.display_name:
                return p.display_name
            break
    user = bundle.users_by_id.get(slot_user_id)
    if user is not None:
        return user.username
    return str(slot_user_id)


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
                "display_name": p.display_name or _participant_label(bundle, p.user_id),
                "consent_status": p.consent_status,
                "turn_order": p.turn_order,
            }
            for p in ordered_participants(bundle.participants)
        ],
        "current_participant_name": (
            _participant_label(bundle, session.current_participant_user_id)
            if session.current_participant_user_id is not None
            else None
        ),
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
    repo: RepositorySubmission | None = None
    if body.repository_submission_id:
        repo = db.get(RepositorySubmission, body.repository_submission_id)
        if repo is None or repo.team_id != team.id:
            raise HTTPException(status_code=400, detail="Repository submission not found for team")
    else:
        candidates = list(
            db.exec(
                select(RepositorySubmission)
                .where(RepositorySubmission.team_id == team.id)
                .order_by(RepositorySubmission.updated_at.desc())
            ).all()
        )
        repo = next(
            (r for r in candidates if r.index_status == RepoIndexStatus.ready.value and r.index_json),
            None,
        )
        if repo is None and candidates:
            raise HTTPException(
                status_code=400,
                detail="Repository index is not ready yet — wait for group setup to finish indexing",
            )
        if repo is None:
            raise HTTPException(
                status_code=400,
                detail="Add group details first (repo, group name, scenario) before starting the interview",
            )
    if repo.index_status != RepoIndexStatus.ready.value or not repo.index_json:
        raise HTTPException(status_code=400, detail="Repository index is not ready")

    raw_names = body.participant_names or list(team.participant_names or [])
    if not raw_names:
        raise HTTPException(
            status_code=400,
            detail="No group member names on this team — set them in Admin → Teams",
        )
    names = _normalize_participant_names(raw_names)
    slot_ids = [_slot_user_id(i) for i in range(len(names))]

    plan = generate_question_plan(
        participant_user_ids=slot_ids,
        index=repo.index_json,
        questions_per_student=body.questions_per_student,
        scenario_slug=team.scenario_slug,
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

    for order, (slot_id, name) in enumerate(zip(slot_ids, names)):
        db.add(
            InterviewParticipant(
                session_id=session.id,
                user_id=slot_id,
                display_name=name,
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


@router.delete("/exit-sessions/{session_id}")
def delete_exit_session(
    session_id: str,
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Delete an exit interview and related answers, assessments, and recording file."""
    bundle = _session_access(db, session_id, user)
    session = bundle.session

    # Clear FK pointer before removing questions.
    session.current_question_id = None
    db.add(session)
    db.flush()

    questions = list(
        db.exec(select(InterviewQuestion).where(InterviewQuestion.session_id == session.id)).all()
    )
    question_ids = [q.id for q in questions]

    # Utterances may reference answers; remove them first.
    for utterance in db.exec(
        select(VoiceUtterance).where(VoiceUtterance.session_id == session.id)
    ).all():
        db.delete(utterance)

    if question_ids:
        for answer in db.exec(
            select(InterviewAnswer).where(InterviewAnswer.question_id.in_(question_ids))  # type: ignore[attr-defined]
        ).all():
            db.delete(answer)

    for question in questions:
        db.delete(question)

    for assessment in db.exec(select(Assessment).where(Assessment.session_id == session.id)).all():
        db.delete(assessment)

    for participant in db.exec(
        select(InterviewParticipant).where(InterviewParticipant.session_id == session.id)
    ).all():
        db.delete(participant)

    recording_path: Path | None = None
    room = db.exec(select(VoiceRoom).where(VoiceRoom.session_id == session.id)).first()
    if room is not None:
        if room.local_file_path:
            recording_path = Path(room.local_file_path)
        db.delete(room)

    db.add(
        AuditEvent(
            actor_id=user.id,
            action="exit_session.delete",
            target_id=str(session.id),
            metadata_json=None,
        )
    )
    db.delete(session)
    db.commit()

    if recording_path is not None:
        try:
            if recording_path.exists():
                recording_path.unlink()
        except OSError:
            pass

    return {"ok": True, "id": session_id}


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
    out: list[dict] = []
    for r in rows:
        participants = list(
            db.exec(
                select(InterviewParticipant)
                .where(InterviewParticipant.session_id == r.id)
                .order_by(InterviewParticipant.turn_order)
            ).all()
        )
        out.append(
            {
                "id": str(r.id),
                "status": r.status,
                "consent_status": r.consent_status,
                "repository_submission_id": str(r.repository_submission_id),
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "participant_names": [p.display_name for p in participants if p.display_name],
            }
        )
    return out


@router.post("/exit-sessions/{session_id}/consent")
def consent(
    session_id: str,
    body: ConsentRequest,
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    bundle = _session_access(db, session_id, user)
    session = bundle.session
    # Shared cohort login: one consent covers every named participant at the laptop.
    now = datetime.now(timezone.utc)
    status_value = ConsentStatus.granted.value if body.granted else ConsentStatus.declined.value
    for participant in bundle.participants:
        participant.consent_status = status_value
        participant.joined_at = now
    session.consent_status = status_value
    if body.granted and session.status in {
        InterviewStatus.scheduled.value,
        InterviewStatus.consent.value,
    }:
        session.status = InterviewStatus.consent.value
    elif not body.granted:
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

    # Skip / leave the active question and advance (voice "next", UI Next).
    if session.status in {
        InterviewStatus.question.value,
        InterviewStatus.optional_probe.value,
        InterviewStatus.response.value,
    }:
        current: InterviewQuestion | None = None
        if session.current_question_id is not None:
            current = db.get(InterviewQuestion, session.current_question_id)

        # Skipping a probe keeps the main answer — only drop the probe turn.
        if session.status == InterviewStatus.optional_probe.value and current is not None:
            current.status = "answered"
            for q in bundle.questions:
                if q.id == current.id:
                    q.status = "answered"
            after_evidence(bundle)
            if session.status == InterviewStatus.student_turn.value and session.current_participant_user_id:
                pending = pending_questions_for(bundle.questions, session.current_participant_user_id)
                if pending:
                    advance_to_question(session, pending[0])
            db.commit()
            return _serialize_session(load_session(db, session_id))  # type: ignore[arg-type]

        alternate: InterviewQuestion | None = None
        if current is not None and current.status in {"asked", "probed", "answered"}:
            # Prefer a follow_up alternate so the student can still meet quota.
            if current.status in {"asked", "probed"}:
                alternate = spawn_skip_alternate(db, current)
            current.status = "skipped"
            for q in bundle.questions:
                if q.id == current.id:
                    q.status = "skipped"

        if alternate is not None:
            advance_to_question(session, alternate)
            db.commit()
            return _serialize_session(load_session(db, session_id))  # type: ignore[arg-type]

        after_evidence(bundle)
        if session.status == InterviewStatus.student_turn.value and session.current_participant_user_id:
            # Reload pending after possible alternate insert on other paths.
            refreshed = load_session(db, session_id)
            assert refreshed is not None
            pending = pending_questions_for(
                refreshed.questions, session.current_participant_user_id
            )
            if pending:
                advance_to_question(session, pending[0])
        db.commit()
        return _serialize_session(load_session(db, session_id))  # type: ignore[arg-type]

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
    if session.status not in {
        InterviewStatus.question.value,
        InterviewStatus.optional_probe.value,
    }:
        raise HTTPException(status_code=400, detail="No active question turn")

    answer = InterviewAnswer(
        question_id=question.id,
        user_id=question.target_user_id,
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
    if question is None:
        raise HTTPException(status_code=404, detail="Question not found")
    db.add(
        InterviewAnswer(
            question_id=question.id,
            user_id=question.target_user_id,
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
    team = db.get(Team, bundle.session.team_id)
    scenario_slug = team.scenario_slug if team else None
    reports = score_session(bundle, sha, scenario_slug=scenario_slug)

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
                "display_name": next(
                    (
                        p.display_name
                        for p in bundle.participants
                        if p.user_id == a.user_id and p.display_name
                    ),
                    str(a.user_id),
                ),
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
