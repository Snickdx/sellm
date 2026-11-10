"""Settings for YAML scenarios + exit interviews / repo / voice / security."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path


def _env_flag(name: str, default: str = "") -> bool:
    return (os.getenv(name, default) or "").strip().lower() in {"1", "true", "yes", "on"}


def _split_csv(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


@dataclass
class Settings:
    llm_provider: str = "heuristic"
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    chat_history_limit: int = 12

    # GitHub / repository ingestion
    github_token: str | None = None
    github_api_base: str = "https://api.github.com"
    github_allowed_orgs: list[str] = field(default_factory=list)
    github_public_only: bool = True
    repo_max_files: int = 400
    repo_max_file_bytes: int = 200_000
    repo_max_total_bytes: int = 8_000_000
    repo_fixture_root: str | None = None

    # Policy / retention notices
    transcript_retention_days: int = 365
    recording_retention_days: int = 30
    team_chat_messages_per_day: int = 400
    team_llm_tokens_per_day: int = 200_000
    llm_budget_alert_usd: float = 5.0

    # Voice / LiveKit
    livekit_url: str | None = None
    livekit_api_key: str | None = None
    livekit_api_secret: str | None = None
    voice_token_ttl_minutes: int = 30
    voice_external_fallback_url: str = "https://meet.jit.si/"
    voice_grading_uses_audio_cues: bool = False
    storage_recordings_dir: str = "./storage/recordings"
    voice_upload_max_bytes: int = 200 * 1024 * 1024

    # Optional S3-compatible sink for LiveKit Cloud egress
    recordings_s3_bucket: str | None = None
    recordings_s3_region: str | None = None
    recordings_s3_access_key: str | None = None
    recordings_s3_secret_key: str | None = None
    recordings_s3_endpoint: str | None = None
    recordings_s3_force_path_style: bool = False

    # Security / HTTP
    allow_default_seed_users: bool = False
    cors_allow_origins: list[str] = field(default_factory=list)
    session_ttl_hours: int = 12
    refuse_default_passwords: bool = False
    rate_limit_login_per_minute: int = 20
    rate_limit_chat_per_minute: int = 60
    rate_limit_upload_per_hour: int = 30

    @property
    def livekit_configured(self) -> bool:
        return bool(self.livekit_url and self.livekit_api_key and self.livekit_api_secret)

    @property
    def recordings_s3_configured(self) -> bool:
        return bool(
            self.recordings_s3_bucket
            and self.recordings_s3_access_key
            and self.recordings_s3_secret_key
        )

    @property
    def fixture_root(self) -> Path:
        if self.repo_fixture_root:
            return Path(self.repo_fixture_root)
        return Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "repos"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        llm_provider=os.getenv("SCENARIO_LLM_PROVIDER", os.getenv("LLM_PROVIDER", "heuristic")).lower(),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        openai_base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        chat_history_limit=int(os.getenv("CHAT_HISTORY_LIMIT", "12")),
        github_token=os.getenv("GITHUB_TOKEN"),
        github_api_base=os.getenv("GITHUB_API_BASE", "https://api.github.com"),
        github_allowed_orgs=[o.lower() for o in _split_csv(os.getenv("GITHUB_ALLOWED_ORGS"))],
        github_public_only=_env_flag("GITHUB_PUBLIC_ONLY", "1"),
        repo_max_files=int(os.getenv("REPO_MAX_FILES", "400")),
        repo_max_file_bytes=int(os.getenv("REPO_MAX_FILE_BYTES", "200000")),
        repo_max_total_bytes=int(os.getenv("REPO_MAX_TOTAL_BYTES", "8000000")),
        repo_fixture_root=os.getenv("REPO_FIXTURE_ROOT"),
        transcript_retention_days=int(os.getenv("TRANSCRIPT_RETENTION_DAYS", "365")),
        recording_retention_days=int(os.getenv("RECORDING_RETENTION_DAYS", "30")),
        team_chat_messages_per_day=int(os.getenv("TEAM_CHAT_MESSAGES_PER_DAY", "400")),
        team_llm_tokens_per_day=int(os.getenv("TEAM_LLM_TOKENS_PER_DAY", "200000")),
        llm_budget_alert_usd=float(os.getenv("LLM_BUDGET_ALERT_USD", "5.0")),
        livekit_url=os.getenv("LIVEKIT_URL"),
        livekit_api_key=os.getenv("LIVEKIT_API_KEY"),
        livekit_api_secret=os.getenv("LIVEKIT_API_SECRET"),
        voice_token_ttl_minutes=int(os.getenv("VOICE_TOKEN_TTL_MINUTES", "30")),
        voice_external_fallback_url=os.getenv("VOICE_EXTERNAL_FALLBACK_URL", "https://meet.jit.si/"),
        storage_recordings_dir=os.getenv("STORAGE_RECORDINGS_DIR", "./storage/recordings"),
        voice_upload_max_bytes=int(os.getenv("VOICE_UPLOAD_MAX_BYTES", str(200 * 1024 * 1024))),
        recordings_s3_bucket=os.getenv("RECORDINGS_S3_BUCKET"),
        recordings_s3_region=os.getenv("RECORDINGS_S3_REGION"),
        recordings_s3_access_key=os.getenv("RECORDINGS_S3_ACCESS_KEY"),
        recordings_s3_secret_key=os.getenv("RECORDINGS_S3_SECRET_KEY"),
        recordings_s3_endpoint=os.getenv("RECORDINGS_S3_ENDPOINT"),
        recordings_s3_force_path_style=os.getenv("RECORDINGS_S3_FORCE_PATH_STYLE", "").lower()
        in {"1", "true", "yes"},
        allow_default_seed_users=_env_flag("ALLOW_DEFAULT_SEED_USERS"),
        cors_allow_origins=_split_csv(os.getenv("CORS_ALLOW_ORIGINS")),
        session_ttl_hours=int(os.getenv("SESSION_TTL_HOURS", "12")),
        refuse_default_passwords=_env_flag("REFUSE_DEFAULT_PASSWORDS")
        or (os.getenv("ENVIRONMENT") or "").strip().lower() in {"prod", "production"},
        rate_limit_login_per_minute=int(os.getenv("RATE_LIMIT_LOGIN_PER_MINUTE", "20")),
        rate_limit_chat_per_minute=int(os.getenv("RATE_LIMIT_CHAT_PER_MINUTE", "60")),
        rate_limit_upload_per_hour=int(os.getenv("RATE_LIMIT_UPLOAD_PER_HOUR", "30")),
    )
