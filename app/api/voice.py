"""Voice room tokens, real LiveKit egress recording, attributed STT."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.api.exit_interviews import _session_access
from app.db import get_db
from app.deps import AuthUser, get_current_user
from app.examiner.state import after_evidence, record_response
from app.models.exit import (
    AuditEvent,
    ConsentStatus,
    InterviewAnswer,
    InterviewQuestion,
    VoiceRecordingStatus,
    VoiceRoom,
    VoiceRoomStatus,
    VoiceUtterance,
)
from app.ops import metrics as ops_metrics
from app.settings import Settings, get_settings
from app.voice.egress import local_recording_path, start_room_composite_egress, stop_egress
from app.voice.tokens import mint_livekit_token, room_name_for_session

router = APIRouter(tags=["voice"])

FORBIDDEN_GRADING_KEYS = frozenset(
    {"accent", "appearance", "vocal_confidence", "tone", "fluency_score", "prosody"}
)


class VoiceStatusOut(BaseModel):
    livekit_configured: bool
    text_fallback: bool = True
    external_fallback_url: str
    grading_uses_audio_cues: bool = False
    room_name: str | None = None
    room_status: str | None = None
    recording_status: str | None = None
    recording_indicator: bool = False
    playback_url: str | None = None
    consent_required: bool = True


class VoiceTokenOut(BaseModel):
    url: str
    token: str
    room_name: str
    identity: str
    recording_indicator: bool
    text_fallback: bool = True


class UtteranceIn(BaseModel):
    text: str = Field(min_length=1, max_length=8000)
    is_final: bool = True
    track_sid: str | None = Field(default=None, max_length=100)


class UtteranceCorrectIn(BaseModel):
    corrected_text: str = Field(min_length=1, max_length=8000)


def _get_or_create_room(db: Session, session_id: str) -> VoiceRoom:
    room = db.exec(select(VoiceRoom).where(VoiceRoom.session_id == session_id)).first()
    if room is not None:
        return room
    room = VoiceRoom(
        session_id=session_id,
        room_name=room_name_for_session(session_id),
        status=VoiceRoomStatus.idle.value,
        recording_status=VoiceRecordingStatus.none.value,
        recording_indicator=False,
    )
    db.add(room)
    db.commit()
    db.refresh(room)
    return room


@router.get("/exit-sessions/{session_id}/voice", response_model=VoiceStatusOut)
def voice_status(
    session_id: str,
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> VoiceStatusOut:
    bundle = _session_access(db, session_id, user)
    room = db.exec(select(VoiceRoom).where(VoiceRoom.session_id == bundle.session.id)).first()
    return VoiceStatusOut(
        livekit_configured=settings.livekit_configured,
        text_fallback=True,
        external_fallback_url=settings.voice_external_fallback_url,
        grading_uses_audio_cues=False,
        room_name=room.room_name if room else room_name_for_session(str(bundle.session.id)),
        room_status=room.status if room else None,
        recording_status=room.recording_status if room else VoiceRecordingStatus.none.value,
        recording_indicator=bool(room.recording_indicator) if room else False,
        playback_url=room.playback_url if room else None,
        consent_required=bundle.session.consent_status != ConsentStatus.granted.value,
    )


@router.post("/exit-sessions/{session_id}/voice/token", response_model=VoiceTokenOut)
def voice_token(
    session_id: str,
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> VoiceTokenOut:
    bundle = _session_access(db, session_id, user)
    if bundle.session.consent_status != ConsentStatus.granted.value:
        raise HTTPException(status_code=400, detail="All participants must consent before joining voice")
    if not settings.livekit_configured:
        raise HTTPException(
            status_code=503,
            detail=(
                "LiveKit is not configured. Use text answers or the external conferencing fallback "
                f"({settings.voice_external_fallback_url})."
            ),
        )

    room = _get_or_create_room(db, bundle.session.id)
    room.status = VoiceRoomStatus.live.value
    db.commit()

    token = mint_livekit_token(
        settings=settings,
        identity=str(user.id),
        name=user.display_name,
        room_name=room.room_name,
    )
    db.add(
        AuditEvent(
            actor_id=user.id,
            action="voice.token_issued",
            target_id=str(bundle.session.id),
            metadata_json=None,
        )
    )
    db.commit()
    assert settings.livekit_url
    return VoiceTokenOut(
        url=settings.livekit_url,
        token=token,
        room_name=room.room_name,
        identity=str(user.id),
        recording_indicator=room.recording_indicator,
        text_fallback=True,
    )


@router.post("/exit-sessions/{session_id}/voice/leave")
def voice_leave(
    session_id: str,
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    bundle = _session_access(db, session_id, user)
    room = db.exec(select(VoiceRoom).where(VoiceRoom.session_id == bundle.session.id)).first()
    db.add(
        AuditEvent(
            actor_id=user.id,
            action="voice.leave",
            target_id=str(bundle.session.id),
            metadata_json=None,
        )
    )
    if room is not None and user.is_instructor:
        room.status = VoiceRoomStatus.ended.value
        room.ended_at = datetime.now(timezone.utc)
        if room.recording_status == VoiceRecordingStatus.recording.value:
            room.recording_status = VoiceRecordingStatus.processing.value
            room.recording_indicator = False
    db.commit()
    return {"ok": True}


@router.post("/exit-sessions/{session_id}/voice/recording/start")
def start_recording(
    session_id: str,
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    bundle = _session_access(db, session_id, user)
    if bundle.session.consent_status != ConsentStatus.granted.value:
        raise HTTPException(status_code=400, detail="Consent required before recording")
    room = _get_or_create_room(db, bundle.session.id)

    # LiveKit Cloud egress needs object storage. Without S3, browser uploads the video.
    use_egress = settings.livekit_configured and settings.recordings_s3_configured
    if use_egress:
        room.recording_status = VoiceRecordingStatus.starting.value
        db.commit()
        try:
            result = start_room_composite_egress(
                settings=settings,
                room_name=room.room_name,
                session_id=bundle.session.id,
            )
            egress_id = result.get("egress_id") or result.get("egressId")
            if not egress_id:
                raise RuntimeError(f"No egress_id in response: {result}")
            room.egress_id = str(egress_id)
            room.recording_status = VoiceRecordingStatus.recording.value
            room.recording_indicator = True
            room.local_file_path = str(local_recording_path(settings, bundle.session.id))
            db.add(
                AuditEvent(
                    actor_id=user.id,
                    action="voice.recording_start",
                    target_id=str(bundle.session.id),
                    metadata_json=f'{{"egress_id":"{room.egress_id}","mode":"egress"}}',
                )
            )
            db.commit()
            return {
                "recording_status": room.recording_status,
                "recording_indicator": room.recording_indicator,
                "egress_id": room.egress_id,
                "mode": "egress",
                "note": "Participants must see the recording indicator before speaking.",
            }
        except Exception as exc:  # noqa: BLE001
            ops_metrics.incr("recording_failures")
            # Fall through to browser capture if egress fails.
            room.egress_id = None
            room.recording_status = VoiceRecordingStatus.failed.value
            room.recording_indicator = False
            db.commit()
            # continue to browser mode below

    room.recording_status = VoiceRecordingStatus.recording.value
    room.recording_indicator = True
    room.local_file_path = str(local_recording_path(settings, bundle.session.id, ext="webm"))
    db.add(
        AuditEvent(
            actor_id=user.id,
            action="voice.recording_start",
            target_id=str(bundle.session.id),
            metadata_json='{"mode":"browser"}',
        )
    )
    db.commit()
    return {
        "recording_status": room.recording_status,
        "recording_indicator": room.recording_indicator,
        "egress_id": room.egress_id,
        "mode": "browser",
        "note": "Browser will capture camera+mic video and upload when the interview ends.",
    }


@router.post("/exit-sessions/{session_id}/voice/recording/upload")
async def upload_recording(
    session_id: str,
    file: UploadFile = File(...),
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """Accept a browser MediaRecorder blob (camera + mic) for the exit session."""
    bundle = _session_access(db, session_id, user)
    if bundle.session.consent_status != ConsentStatus.granted.value:
        raise HTTPException(status_code=400, detail="Consent required before uploading recording")

    filename = file.filename or "recording.webm"
    ext = Path(filename).suffix.lstrip(".") or "webm"
    if ext.lower() not in {"webm", "mp4", "mkv", "ogg"}:
        raise HTTPException(status_code=400, detail="Unsupported recording format")

    dest = local_recording_path(settings, bundle.session.id, ext=ext)
    max_bytes = int(settings.voice_upload_max_bytes or (200 * 1024 * 1024))
    content_length = file.headers.get("content-length") if file.headers else None
    if content_length and content_length.isdigit() and int(content_length) > max_bytes:
        raise HTTPException(status_code=413, detail=f"Recording exceeds max size ({max_bytes} bytes)")
    from app.security.rate_limit import rate_limiter

    if not rate_limiter.allow(
        "voice_upload",
        str(user.id),
        limit=get_settings().rate_limit_upload_per_hour,
        window_seconds=3600,
    ):
        raise HTTPException(status_code=429, detail="Upload rate limit exceeded")

    chunks: list[bytes] = []
    total = 0
    while True:
        piece = await file.read(1024 * 1024)
        if not piece:
            break
        total += len(piece)
        if total > max_bytes:
            raise HTTPException(status_code=413, detail=f"Recording exceeds max size ({max_bytes} bytes)")
        chunks.append(piece)
    data = b"".join(chunks)
    if not data:
        raise HTTPException(status_code=400, detail="Empty recording upload")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)

    room = _get_or_create_room(db, bundle.session.id)
    room.local_file_path = str(dest.resolve())
    room.recording_status = VoiceRecordingStatus.ready.value
    room.recording_indicator = False
    room.playback_url = f"/api/exit-sessions/{bundle.session.id}/recording"
    db.add(
        AuditEvent(
            actor_id=user.id,
            action="voice.recording_upload",
            target_id=str(bundle.session.id),
            metadata_json=f'{{"bytes":{len(data)},"path":"{dest.name}"}}',
        )
    )
    db.commit()
    return {
        "recording_status": room.recording_status,
        "recording_indicator": False,
        "playback_url": room.playback_url,
        "bytes": len(data),
    }


@router.post("/exit-sessions/{session_id}/voice/recording/stop")
def stop_recording(
    session_id: str,
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    bundle = _session_access(db, session_id, user)
    room = _get_or_create_room(db, bundle.session.id)
    room.recording_indicator = False
    room.recording_status = VoiceRecordingStatus.processing.value
    db.commit()

    if room.egress_id and settings.livekit_configured:
        try:
            stop_egress(settings=settings, egress_id=room.egress_id)
        except Exception as exc:  # noqa: BLE001
            ops_metrics.incr("recording_failures")
            room.recording_status = VoiceRecordingStatus.failed.value
            db.commit()
            raise HTTPException(status_code=502, detail=f"Failed to stop recording: {exc}") from exc

    local_path = Path(room.local_file_path) if room.local_file_path else local_recording_path(
        settings, bundle.session.id
    )
    room.playback_url = f"/api/admin/exit-sessions/{bundle.session.id}/recording"
    if local_path.exists():
        room.local_file_path = str(local_path)
        room.recording_status = VoiceRecordingStatus.ready.value
    elif settings.recordings_s3_configured:
        # File lands in S3; playback endpoint may proxy later — mark ready with API URL.
        room.recording_status = VoiceRecordingStatus.ready.value
    else:
        # Browser upload may still be in flight; leave processing until upload lands.
        if room.egress_id:
            room.recording_status = VoiceRecordingStatus.ready.value
            room.local_file_path = str(local_path)
        else:
            room.recording_status = VoiceRecordingStatus.processing.value
            room.local_file_path = str(local_path)

    db.add(
        AuditEvent(
            actor_id=user.id,
            action="voice.recording_stop",
            target_id=str(bundle.session.id),
            metadata_json=None,
        )
    )
    db.commit()
    return {
        "recording_status": room.recording_status,
        "playback_url": room.playback_url,
        "recording_indicator": False,
    }


@router.get("/admin/exit-sessions/{session_id}/recording")
@router.get("/exit-sessions/{session_id}/recording")
def download_recording(
    session_id: str,
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    # Recording download is instructor-only (admin route + student-facing alias).
    if not user.is_instructor:
        raise HTTPException(status_code=403, detail="Instructor role required to download recordings")
    bundle = _session_access(db, session_id, user)
    room = db.exec(select(VoiceRoom).where(VoiceRoom.session_id == bundle.session.id)).first()
    if room is None:
        raise HTTPException(status_code=404, detail="No recording for session")

    candidates: list[Path] = []
    if room.local_file_path:
        candidates.append(Path(room.local_file_path))
        # Older rows may store a CWD-relative path; also try resolved.
        rel = Path(room.local_file_path)
        if not rel.is_absolute():
            candidates.append((Path.cwd() / rel).resolve())
    for ext in ("webm", "mp4", "mkv", "ogg"):
        candidates.append(local_recording_path(settings, bundle.session.id, ext=ext))

    path = next((p for p in candidates if p.exists()), None)
    if path is None:
        detail = "Recording file not found on disk."
        if room.recording_status == VoiceRecordingStatus.processing.value:
            detail = "Recording still processing — try again shortly."
        elif room.recording_status == VoiceRecordingStatus.ready.value:
            detail = "Recording was marked ready but the file is missing on the server."
        raise HTTPException(status_code=404, detail=detail)
    suffix = path.suffix.lower()
    media = "video/webm" if suffix == ".webm" else "video/mp4"
    return FileResponse(path, media_type=media, filename=path.name)


@router.post("/exit-sessions/{session_id}/voice/utterances")
def post_utterance(
    session_id: str,
    body: UtteranceIn,
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    bundle = _session_access(db, session_id, user)
    payload = body.model_dump()
    if FORBIDDEN_GRADING_KEYS & set(payload.keys()):
        raise HTTPException(status_code=400, detail="Audio grading cues are not accepted")

    row = VoiceUtterance(
        session_id=bundle.session.id,
        user_id=user.id,
        text=body.text.strip(),
        is_final=body.is_final,
        track_sid=body.track_sid,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {
        "id": str(row.id),
        "user_id": row.user_id,
        "text": row.text,
        "is_final": row.is_final,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.patch("/exit-sessions/{session_id}/voice/utterances/{utterance_id}")
def correct_utterance(
    session_id: str,
    utterance_id: str,
    body: UtteranceCorrectIn,
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    bundle = _session_access(db, session_id, user)
    row = db.get(VoiceUtterance, utterance_id)
    if row is None or row.session_id != bundle.session.id:
        raise HTTPException(status_code=404, detail="Utterance not found")
    row.corrected_text = body.corrected_text.strip()
    db.commit()
    return {"id": str(row.id), "corrected_text": row.corrected_text}


@router.post("/exit-sessions/{session_id}/voice/utterances/{utterance_id}/commit-answer")
def commit_utterance_as_answer(
    session_id: str,
    utterance_id: str,
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    bundle = _session_access(db, session_id, user)
    row = db.get(VoiceUtterance, utterance_id)
    if row is None or row.session_id != bundle.session.id:
        raise HTTPException(status_code=404, detail="Utterance not found")
    if bundle.session.current_question_id is None:
        raise HTTPException(status_code=400, detail="No active question")

    question = db.get(InterviewQuestion, bundle.session.current_question_id)
    if question is None:
        raise HTTPException(status_code=400, detail="Question missing")

    text = (row.corrected_text or row.text).strip()
    answer = InterviewAnswer(
        question_id=question.id,
        user_id=question.target_user_id,
        modality="voice_stt",
        text=text,
        is_probe=False,
    )
    db.add(answer)
    db.flush()
    record_response(bundle.session, question)
    for q in bundle.questions:
        if q.id == question.id:
            q.status = question.status
    after_evidence(bundle)
    row.committed_answer_id = answer.id
    db.commit()
    return {
        "answer_id": str(answer.id),
        "text": text,
        "note": "Answer stored as text evidence only — no vocal cues used for scoring.",
    }


@router.get("/exit-sessions/{session_id}/voice/utterances")
def list_utterances(
    session_id: str,
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    bundle = _session_access(db, session_id, user)
    rows = list(
        db.exec(
            select(VoiceUtterance)
            .where(VoiceUtterance.session_id == bundle.session.id)
            .order_by(VoiceUtterance.created_at.asc())
        ).all()
    )
    return [
        {
            "id": str(r.id),
            "user_id": r.user_id,
            "text": r.corrected_text or r.text,
            "raw_text": r.text,
            "corrected_text": r.corrected_text,
            "is_final": r.is_final,
            "committed_answer_id": str(r.committed_answer_id) if r.committed_answer_id else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
