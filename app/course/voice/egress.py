"""LiveKit room-composite egress helpers (real recording, not stubs)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import httpx

from app.course.settings import Settings
from app.course.voice.tokens import livekit_http_base, mint_livekit_api_token

logger = logging.getLogger(__name__)


def _headers(settings: Settings) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {mint_livekit_api_token(settings=settings)}",
        "Content-Type": "application/json",
    }


def _file_output(settings: Settings, session_id: str) -> dict[str, Any]:
    """Prefer S3 when configured (LiveKit Cloud); else local filepath for self-hosted egress."""
    filename = f"exit-{session_id}.mp4"
    if settings.recordings_s3_configured:
        s3: dict[str, Any] = {
            "access_key": settings.recordings_s3_access_key,
            "secret": settings.recordings_s3_secret_key,
            "bucket": settings.recordings_s3_bucket,
            "region": settings.recordings_s3_region or "auto",
            "force_path_style": settings.recordings_s3_force_path_style,
        }
        if settings.recordings_s3_endpoint:
            s3["endpoint"] = settings.recordings_s3_endpoint
        return {
            "file": {
                "file_type": "MP4",
                "filepath": f"exit-interviews/{filename}",
                "s3": s3,
            }
        }

    out_dir = Path(settings.storage_recordings_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    filepath = str((out_dir / filename).resolve())
    return {
        "file": {
            "file_type": "MP4",
            "filepath": filepath,
        }
    }


def start_room_composite_egress(*, settings: Settings, room_name: str, session_id: str) -> dict[str, Any]:
    if not settings.livekit_configured:
        raise RuntimeError("LiveKit is not configured")
    base = livekit_http_base(settings)
    body = {
        "room_name": room_name,
        "layout": "grid",
        "audio_only": False,
        "file_outputs": [_file_output(settings, session_id)["file"]],
    }
    # LiveKit twirp expects EncodedOutputs shape; support both file_outputs and file.
    payload = {
        "room_name": room_name,
        "layout": "grid",
        "audio_only": False,
        "file": _file_output(settings, session_id)["file"],
    }
    url = f"{base}/twirp/livekit.Egress/StartRoomCompositeEgress"
    with httpx.Client(timeout=30.0) as client:
        response = client.post(url, headers=_headers(settings), json=payload)
        if response.status_code >= 400:
            # Retry with plural file_outputs for newer APIs
            response = client.post(url, headers=_headers(settings), json={**body, "file": None})
            if response.status_code >= 400:
                logger.error("egress_start_failed status=%s body=%s", response.status_code, response.text)
                raise RuntimeError(f"LiveKit egress start failed: {response.status_code} {response.text[:300]}")
        data = response.json()
    return data


def stop_egress(*, settings: Settings, egress_id: str) -> dict[str, Any]:
    if not settings.livekit_configured:
        raise RuntimeError("LiveKit is not configured")
    base = livekit_http_base(settings)
    url = f"{base}/twirp/livekit.Egress/StopEgress"
    with httpx.Client(timeout=30.0) as client:
        response = client.post(
            url,
            headers=_headers(settings),
            json={"egress_id": egress_id},
        )
        if response.status_code >= 400:
            logger.error("egress_stop_failed status=%s body=%s", response.status_code, response.text)
            raise RuntimeError(f"LiveKit egress stop failed: {response.status_code} {response.text[:300]}")
        return response.json()


def local_recording_path(settings: Settings, session_id: str, *, ext: str = "mp4") -> Path:
    safe_ext = (ext or "mp4").lstrip(".").lower() or "mp4"
    out_dir = Path(settings.storage_recordings_dir)
    if not out_dir.is_absolute():
        out_dir = (Path.cwd() / out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / f"exit-{session_id}.{safe_ext}"
