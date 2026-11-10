"""Explicit exit-interview state transitions (kept outside the LLM)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import Session, select

from app.seproject.exit_models import (
    Assessment,
    ConsentStatus,
    ExitInterviewSession,
    InterviewAnswer,
    InterviewParticipant,
    InterviewQuestion,
    InterviewStatus,
)
from app.storage.conversation_store import User


ACTIVE_QUESTION_STATUSES = {"asked", "probed"}


class SessionBundle:
    """Exit session plus eagerly loaded children (SQLModel has no relationships)."""

    def __init__(
        self,
        session: ExitInterviewSession,
        participants: list[InterviewParticipant],
        questions: list[InterviewQuestion],
        answers_by_question: dict[str, list[InterviewAnswer]],
        assessments: list[Assessment],
        users_by_id: dict[int, User],
    ) -> None:
        self.session = session
        self.participants = participants
        self.questions = questions
        self.answers_by_question = answers_by_question
        self.assessments = assessments
        self.users_by_id = users_by_id

    def answers_for(self, question_id: str) -> list[InterviewAnswer]:
        return self.answers_by_question.get(question_id, [])


def all_participants_consented(participants: list[InterviewParticipant]) -> bool:
    return bool(participants) and all(p.consent_status == ConsentStatus.granted.value for p in participants)


def ordered_participants(participants: list[InterviewParticipant]) -> list[InterviewParticipant]:
    return sorted(participants, key=lambda p: p.turn_order)


def pending_questions_for(questions: list[InterviewQuestion], user_id: int) -> list[InterviewQuestion]:
    return sorted(
        [q for q in questions if q.target_user_id == user_id and q.status == "pending"],
        key=lambda q: q.sequence,
    )


def next_participant_with_work(
    participants: list[InterviewParticipant], questions: list[InterviewQuestion]
) -> InterviewParticipant | None:
    for participant in ordered_participants(participants):
        if pending_questions_for(questions, participant.user_id):
            return participant
    return None


def start_session(bundle: SessionBundle) -> None:
    session = bundle.session
    if session.status not in {
        InterviewStatus.scheduled.value,
        InterviewStatus.consent.value,
        InterviewStatus.introductions.value,
    }:
        raise ValueError(f"Cannot start from status={session.status}")
    if not all_participants_consented(bundle.participants):
        session.status = InterviewStatus.consent.value
        return
    session.status = InterviewStatus.introductions.value
    session.started_at = session.started_at or datetime.now(timezone.utc)
    participant = next_participant_with_work(bundle.participants, bundle.questions)
    if participant is None:
        session.status = InterviewStatus.closing.value
        return
    session.current_participant_user_id = participant.user_id
    session.status = InterviewStatus.student_turn.value


def advance_to_question(session: ExitInterviewSession, question: InterviewQuestion) -> None:
    session.current_question_id = question.id
    session.current_participant_user_id = question.target_user_id
    question.status = "asked"
    session.status = InterviewStatus.question.value


def record_response(session: ExitInterviewSession, question: InterviewQuestion) -> None:
    question.status = "answered"
    session.status = InterviewStatus.response.value


def optional_probe(session: ExitInterviewSession, question: InterviewQuestion) -> None:
    question.status = "probed"
    session.status = InterviewStatus.optional_probe.value


def after_evidence(bundle: SessionBundle) -> None:
    session = bundle.session
    session.status = InterviewStatus.evidence_recorded.value
    if session.current_participant_user_id is None:
        session.status = InterviewStatus.closing.value
        return
    remaining = pending_questions_for(bundle.questions, session.current_participant_user_id)
    if remaining:
        session.status = InterviewStatus.student_turn.value
        session.current_question_id = None
        return
    session.status = InterviewStatus.next_student.value
    session.current_question_id = None
    nxt = next_participant_with_work(bundle.participants, bundle.questions)
    if nxt is None:
        session.status = InterviewStatus.closing.value
        session.current_participant_user_id = None
        return
    session.current_participant_user_id = nxt.user_id
    session.status = InterviewStatus.student_turn.value


def begin_processing(session: ExitInterviewSession) -> None:
    session.status = InterviewStatus.processing.value
    session.ended_at = datetime.now(timezone.utc)


def mark_lecturer_review(session: ExitInterviewSession) -> None:
    session.status = InterviewStatus.lecturer_review.value


def finalize_session(session: ExitInterviewSession) -> None:
    session.status = InterviewStatus.finalized.value


def load_session(db: Session, session_id: str) -> SessionBundle | None:
    session = db.get(ExitInterviewSession, session_id)
    if session is None:
        return None
    participants = list(
        db.exec(
            select(InterviewParticipant)
            .where(InterviewParticipant.session_id == session_id)
            .order_by(InterviewParticipant.turn_order)
        ).all()
    )
    questions = list(
        db.exec(
            select(InterviewQuestion)
            .where(InterviewQuestion.session_id == session_id)
            .order_by(InterviewQuestion.sequence)
        ).all()
    )
    qids = [q.id for q in questions]
    answers_by_question: dict[str, list[InterviewAnswer]] = {qid: [] for qid in qids}
    if qids:
        answers = list(db.exec(select(InterviewAnswer).where(InterviewAnswer.question_id.in_(qids))).all())
        for a in answers:
            answers_by_question.setdefault(a.question_id, []).append(a)
        for qid in answers_by_question:
            answers_by_question[qid].sort(key=lambda a: a.created_at or datetime.min.replace(tzinfo=timezone.utc))
    assessments = list(db.exec(select(Assessment).where(Assessment.session_id == session_id)).all())
    user_ids = {p.user_id for p in participants} | {q.target_user_id for q in questions}
    users_by_id: dict[int, User] = {}
    if user_ids:
        for u in db.exec(select(User).where(User.id.in_(list(user_ids)))).all():
            if u.id is not None:
                users_by_id[int(u.id)] = u
    return SessionBundle(session, participants, questions, answers_by_question, assessments, users_by_id)


def unanswered_question_ids(questions: list[InterviewQuestion]) -> list[str]:
    return [str(q.id) for q in questions if q.status in {"pending", "asked", "probed"}]
