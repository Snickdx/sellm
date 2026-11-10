"""Public policy text for consent, retention, and accessibility."""

from __future__ import annotations

from typing import Any

from app.settings import Settings


def policy_document(settings: Settings) -> dict[str, Any]:
    return {
        "version": "2026-11-m7",
        "consent": {
            "title": "Exit interview recording & assessment consent",
            "summary": (
                "Exit interviews capture your typed answers (and, if enabled later, "
                "voice/video) for competency assessment. Answers are treated as untrusted "
                "data, not instructions to the examiner. Provisional AI scores are reviewed "
                "by an instructor before marks are final."
            ),
            "bullets": [
                "Participation requires explicit consent before the session starts.",
                "You may decline; the session cannot proceed without consent from all listed participants.",
                "Do not share passwords or personal secrets in answers.",
                "Appearance, accent, and vocal confidence are never used for grading (text-first pilot).",
            ],
        },
        "retention": {
            "transcript_days": settings.transcript_retention_days,
            "recording_days": settings.recording_retention_days,
            "summary": (
                f"Interview transcripts are retained for approximately "
                f"{settings.transcript_retention_days} days. Any future room recordings "
                f"are retained for approximately {settings.recording_retention_days} days, "
                "then deleted unless a longer hold is required for academic appeals."
            ),
            "deletion": (
                "Instructors may request early deletion after marking. Students requesting "
                "deletion should contact the course instructor; appeals may pause deletion."
            ),
        },
        "accessibility": {
            "text_only_supported": True,
            "low_bandwidth": (
                "The pilot is text-first. Disable optional media features if connectivity is poor. "
                "Prefer the heuristic LLM provider when hosted model latency is high."
            ),
            "notes": [
                "Keyboard-accessible forms and links are required for core flows.",
                "Voice/video (M6) is optional; typed answers always work.",
                "Grading never uses appearance, accent, or vocal confidence.",
            ],
        },
        "voice": {
            "optional": True,
            "text_fallback": True,
            "grading_uses_audio_cues": False,
            "recording_requires_consent": True,
        },
        "quotas": {
            "team_chat_messages_per_day": settings.team_chat_messages_per_day,
            "team_llm_tokens_per_day": settings.team_llm_tokens_per_day,
            "llm_budget_alert_usd": settings.llm_budget_alert_usd,
        },
    }
