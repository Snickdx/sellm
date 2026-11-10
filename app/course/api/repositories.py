"""Team repository submission, analyze, status, and retrieval (self-service)."""

from __future__ import annotations

import os

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.course.db import get_db
from app.course.deps import AuthUser, ensure_team_access, get_current_user
from app.course.exit_models import AuditEvent, RepoIndexStatus, RepositorySubmission, Team, TeamMember
from app.course.providers.github import get_repository_provider, parse_repo_url
from app.course.repo.ingest import analyze_submission, analyze_submission_job
from app.course.repo.retrieval import (
    get_file,
    get_symbol,
    get_tests,
    search_code,
    strip_contents_for_api,
)
from app.course.settings import get_settings

router = APIRouter(tags=["repositories"])


class RepositorySubmitRequest(BaseModel):
    github_url: str = Field(min_length=3, max_length=500)
    # Optional — when omitted, the default-branch tip is resolved automatically.
    commit_sha: str | None = Field(default=None, max_length=64)
    branch: str | None = Field(default=None, max_length=200)
    analyze_now: bool = True


class RepositoryOut(BaseModel):
    id: str
    team_id: str
    github_url: str
    owner: str
    repo: str
    branch: str | None
    commit_sha: str
    index_status: str
    index_error: str | None
    attempt_count: int
    summary: dict | None = None


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=20, ge=1, le=100)


def _to_out(row: RepositorySubmission) -> RepositoryOut:
    return RepositoryOut(
        id=row.id,
        team_id=row.team_id,
        github_url=row.github_url,
        owner=row.owner,
        repo=row.repo,
        branch=row.branch,
        commit_sha=row.commit_sha,
        index_status=row.index_status,
        index_error=row.index_error,
        attempt_count=row.attempt_count,
        summary=row.summary_json,
    )


def _repo_access(db: Session, repo_id: str, user: AuthUser) -> RepositorySubmission:
    row = db.get(RepositorySubmission, repo_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Repository not found")
    ensure_team_access(db, row.team_id, user)
    return row


@router.post("/admin/teams/{team_id}/repository", response_model=RepositoryOut, status_code=201)
@router.post("/teams/{team_id}/repository", response_model=RepositoryOut, status_code=201)
def submit_repository(
    team_id: str,
    body: RepositorySubmitRequest,
    background: BackgroundTasks,
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RepositoryOut:
    team = ensure_team_access(db, team_id, user)

    try:
        ref = parse_repo_url(body.github_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    settings = get_settings()
    provider = get_repository_provider(settings, ref)
    branch = (body.branch or "").strip() or None
    raw_sha = (body.commit_sha or "").strip()
    try:
        if not raw_sha or raw_sha.upper() == "HEAD":
            head = provider.resolve_head(ref, branch)
            sha = str(head.get("sha") or "").strip().lower()
            if not sha:
                raise FileNotFoundError("Could not resolve repository HEAD")
            if not branch and head.get("branch"):
                branch = str(head["branch"])
        else:
            sha = raw_sha.lower()
            meta = provider.verify_commit(ref, sha)
            sha = str(meta.get("sha") or sha).strip().lower()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    existing = db.exec(
        select(RepositorySubmission).where(
            RepositorySubmission.team_id == team.id,
            RepositorySubmission.commit_sha == sha,
        )
    ).first()
    if existing is None:
        existing = db.exec(
            select(RepositorySubmission).where(
                RepositorySubmission.team_id == team.id,
                RepositorySubmission.github_url == ref.display_url,
            )
        ).first()
    if existing is None and len(sha) >= 7:
        existing = db.exec(
            select(RepositorySubmission).where(
                RepositorySubmission.team_id == team.id,
                RepositorySubmission.commit_sha.startswith(sha[:7]),
            )
        ).first()

    display_url = ref.display_url if ref.source == "github" else body.github_url.strip()
    if existing is not None:
        row = existing
        row.github_url = display_url
        row.branch = branch
        row.owner = ref.owner
        row.repo = ref.repo
        if (
            row.index_status == RepoIndexStatus.ready.value
            and row.commit_sha == sha
        ):
            db.commit()
            db.refresh(row)
            return _to_out(row)
        row.commit_sha = sha
        row.index_status = RepoIndexStatus.pending.value
        row.index_error = None
    else:
        row = RepositorySubmission(
            team_id=team.id,
            github_url=display_url,
            owner=ref.owner,
            repo=ref.repo,
            branch=branch,
            commit_sha=sha,
            index_status=RepoIndexStatus.pending.value,
        )
        db.add(row)

    db.add(
        AuditEvent(
            actor_id=user.id,
            action="repository.submit",
            target_id=str(team.id),
            metadata_json=f'{{"url":"{row.github_url}","sha":"{sha}"}}',
        )
    )
    db.commit()
    db.refresh(row)

    if body.analyze_now:
        if os.getenv("TESTING") == "1":
            analyze_submission(db, row.id)
            db.refresh(row)
        else:
            background.add_task(analyze_submission_job, row.id)

    return _to_out(row)


@router.post("/admin/repositories/{repo_id}/analyze", response_model=RepositoryOut)
@router.post("/repositories/{repo_id}/analyze", response_model=RepositoryOut)
def analyze_repository(
    repo_id: str,
    background: BackgroundTasks,
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RepositoryOut:
    row = _repo_access(db, repo_id, user)
    if os.getenv("TESTING") == "1":
        analyze_submission(db, row.id)
        db.refresh(row)
    else:
        background.add_task(analyze_submission_job, row.id)
        row.index_status = RepoIndexStatus.pending.value
        db.commit()
        db.refresh(row)
    return _to_out(row)


@router.get("/admin/repositories/{repo_id}/status", response_model=RepositoryOut)
@router.get("/repositories/{repo_id}/status", response_model=RepositoryOut)
def repository_status(
    repo_id: str,
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RepositoryOut:
    return _to_out(_repo_access(db, repo_id, user))


@router.get("/admin/teams/{team_id}/repositories", response_model=list[RepositoryOut])
@router.get("/teams/{team_id}/repositories", response_model=list[RepositoryOut])
def list_team_repositories(
    team_id: str,
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[RepositoryOut]:
    ensure_team_access(db, team_id, user)
    rows = list(
        db.exec(
            select(RepositorySubmission)
            .where(RepositorySubmission.team_id == team_id)
            .order_by(RepositorySubmission.frozen_at.desc())
        ).all()
    )
    return [_to_out(r) for r in rows]


@router.get("/admin/repositories/{repo_id}/index")
@router.get("/repositories/{repo_id}/index")
def repository_index(
    repo_id: str,
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    row = _repo_access(db, repo_id, user)
    return strip_contents_for_api(row.index_json)


@router.post("/admin/repositories/{repo_id}/search")
@router.post("/repositories/{repo_id}/search")
def repository_search(
    repo_id: str,
    body: SearchRequest,
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    row = _repo_access(db, repo_id, user)
    try:
        return search_code(row.index_json, body.query, limit=body.limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/admin/repositories/{repo_id}/file")
@router.get("/repositories/{repo_id}/file")
def repository_file(
    repo_id: str,
    path: str,
    start_line: int | None = None,
    end_line: int | None = None,
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    row = _repo_access(db, repo_id, user)
    try:
        return get_file(row.index_json, path, start_line=start_line, end_line=end_line)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/admin/repositories/{repo_id}/symbol")
@router.get("/repositories/{repo_id}/symbol")
def repository_symbol(
    repo_id: str,
    name: str,
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    row = _repo_access(db, repo_id, user)
    try:
        return get_symbol(row.index_json, name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/admin/repositories/{repo_id}/tests")
@router.get("/repositories/{repo_id}/tests")
def repository_tests(
    repo_id: str,
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    row = _repo_access(db, repo_id, user)
    try:
        return get_tests(row.index_json)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
