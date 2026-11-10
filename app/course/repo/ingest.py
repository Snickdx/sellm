"""Orchestrate verify + index for a RepositorySubmission."""

from __future__ import annotations

import logging

from sqlmodel import Session

from app.course.db import get_engine
from app.models.exit import RepoIndexStatus, RepositorySubmission
from app.course.providers.github import get_repository_provider, parse_repo_url
from app.course.repo.indexer import build_index
from app.course.settings import Settings, get_settings

logger = logging.getLogger(__name__)


def analyze_submission(
    db: Session, submission_id: str, settings: Settings | None = None
) -> RepositorySubmission:
    settings = settings or get_settings()
    submission = db.get(RepositorySubmission, submission_id)
    if submission is None:
        raise LookupError("Repository submission not found")

    submission.index_status = RepoIndexStatus.running.value
    submission.index_error = None
    submission.attempt_count = int(submission.attempt_count or 0) + 1
    db.commit()

    try:
        ref = parse_repo_url(submission.github_url)
        provider = get_repository_provider(settings, ref)
        index, summary = build_index(
            provider=provider,
            ref=ref,
            sha=submission.commit_sha,
            settings=settings,
        )
        resolved = index.get("commit_sha") or submission.commit_sha
        submission.commit_sha = resolved
        submission.owner = ref.owner
        submission.repo = ref.repo
        submission.index_json = index
        submission.summary_json = summary
        submission.index_status = RepoIndexStatus.ready.value
        submission.index_error = None
        db.commit()
        db.refresh(submission)
        return submission
    except Exception as exc:  # noqa: BLE001
        logger.exception("repository_analyze_failed", extra={"submission_id": str(submission_id)})
        submission.index_status = RepoIndexStatus.failed.value
        submission.index_error = str(exc)
        db.commit()
        db.refresh(submission)
        return submission


def analyze_submission_job(submission_id: str) -> None:
    """Background task entrypoint with its own DB session."""
    with Session(get_engine()) as db:
        analyze_submission(db, submission_id)
