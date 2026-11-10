"""Teams — admin assigns a cohort credential; students fill group details."""

from __future__ import annotations

import os
import secrets

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.course.db import get_db
from app.course.deps import AuthUser, ensure_team_access, get_current_user, require_instructor
from app.course.exit_models import (
    AuditEvent,
    RepoIndexStatus,
    RepositorySubmission,
    Team,
    TeamMember,
)
from app.course.providers.github import get_repository_provider, parse_repo_url
from app.course.repo.ingest import analyze_submission, analyze_submission_job
from app.course.settings import get_settings
from app.storage.conversation_store import User

router = APIRouter(tags=["teams"])


class TeamCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    scenario_slug: str | None = None
    scenario_version: str | None = None
    # Cohort username that owns/shares this team login (required for admin create).
    owner_username: str | None = None
    member_usernames: list[str] = Field(default_factory=list)
    # Real names used when students start the exit interview.
    participant_names: list[str] = Field(default_factory=list)
    github_url: str | None = Field(default=None, max_length=500)
    branch: str | None = Field(default=None, max_length=200)


class TeamUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    scenario_slug: str | None = None
    scenario_version: str | None = None
    participant_names: list[str] | None = None
    github_url: str | None = Field(default=None, max_length=500)
    branch: str | None = Field(default=None, max_length=200)
    analyze_now: bool = True


class TeamMembersRequest(BaseModel):
    usernames: list[str] = Field(min_length=1)


class TeamMemberOut(BaseModel):
    user_id: int
    username: str
    display_name: str
    role: str


class TeamOut(BaseModel):
    id: str
    name: str
    scenario_slug: str | None
    scenario_version: str | None
    participant_names: list[str] = Field(default_factory=list)
    created_at: str | None


class TeamDetailOut(TeamOut):
    members: list[TeamMemberOut]
    repository: dict | None = None


class GroupSetupRequest(BaseModel):
    """Group settings on the exit interview page: name + repo (no commit hash)."""

    name: str = Field(min_length=1, max_length=200)
    github_url: str = Field(min_length=3, max_length=500)
    scenario_slug: str | None = Field(default=None, max_length=120)
    branch: str | None = Field(default=None, max_length=200)
    scenario_version: str | None = None
    analyze_now: bool = True
    team_id: str | None = None


class GroupSetupOut(BaseModel):
    team: TeamDetailOut
    repository: dict


def _normalize_names(names: list[str] | None) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in names or []:
        name = " ".join(str(raw).split()).strip()
        if not name:
            continue
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(name)
    return cleaned


def _repo_out(row: RepositorySubmission | None) -> dict | None:
    if row is None:
        return None
    return {
        "id": row.id,
        "team_id": row.team_id,
        "github_url": row.github_url,
        "owner": row.owner,
        "repo": row.repo,
        "branch": row.branch,
        "commit_sha": row.commit_sha,
        "index_status": row.index_status,
        "index_error": row.index_error,
        "attempt_count": row.attempt_count,
        "summary": row.summary_json,
    }


def _team_out(team: Team) -> TeamOut:
    return TeamOut(
        id=team.id,
        name=team.name,
        scenario_slug=team.scenario_slug,
        scenario_version=team.scenario_version,
        participant_names=list(team.participant_names or []),
        created_at=team.created_at.isoformat() if team.created_at else None,
    )


def _latest_repo(db: Session, team_id: str) -> RepositorySubmission | None:
    return db.exec(
        select(RepositorySubmission)
        .where(RepositorySubmission.team_id == team_id)
        .order_by(RepositorySubmission.updated_at.desc())
    ).first()


def _team_detail(db: Session, team: Team) -> TeamDetailOut:
    members_rows = list(db.exec(select(TeamMember).where(TeamMember.team_id == team.id)).all())
    users: dict[int, User] = {}
    if members_rows:
        for u in db.exec(select(User).where(User.id.in_([m.user_id for m in members_rows]))).all():
            if u.id is not None:
                users[int(u.id)] = u
    members = [
        TeamMemberOut(
            user_id=m.user_id,
            username=users[m.user_id].username if m.user_id in users else str(m.user_id),
            display_name=users[m.user_id].username if m.user_id in users else str(m.user_id),
            role=getattr(users.get(m.user_id), "role", "student") or "student",
        )
        for m in members_rows
    ]
    base = _team_out(team)
    return TeamDetailOut(
        **base.model_dump(),
        members=members,
        repository=_repo_out(_latest_repo(db, team.id)),
    )


def _unique_invite(db: Session) -> str:
    invite_code = secrets.token_hex(4).upper()
    while db.exec(select(Team).where(Team.invite_code == invite_code)).first() is not None:
        invite_code = secrets.token_hex(4).upper()
    return invite_code


def _resolve_username(db: Session, username: str) -> User:
    uname = username.strip()
    if not uname:
        raise HTTPException(status_code=400, detail="Username required")
    user = db.exec(select(User).where(User.username == uname)).first()
    if user is None or user.id is None:
        raise HTTPException(status_code=400, detail=f"Unknown username: {uname}")
    return user


def _add_member(db: Session, team_id: str, user_id: int, existing: set[int]) -> None:
    if user_id in existing:
        return
    db.add(TeamMember(team_id=team_id, user_id=user_id))
    existing.add(user_id)


def _maybe_analyze(background: BackgroundTasks, row: RepositorySubmission) -> None:
    if row.index_status == RepoIndexStatus.ready.value:
        return
    if os.getenv("TESTING") == "1":
        return
    background.add_task(analyze_submission_job, row.id)


@router.post("/admin/teams", response_model=TeamDetailOut, status_code=status.HTTP_201_CREATED)
def create_team_admin(
    body: TeamCreateRequest,
    background: BackgroundTasks,
    instructor: AuthUser = Depends(require_instructor),
    db: Session = Depends(get_db),
) -> TeamDetailOut:
    """Admin creates a team: cohort owner, scenario, repo, and interview member names."""
    owner_name = (body.owner_username or "").strip()
    if not owner_name:
        raise HTTPException(
            status_code=400,
            detail="owner_username is required — pick the cohort login that shares this team",
        )
    owner = _resolve_username(db, owner_name)

    names = _normalize_names(body.participant_names)
    team = Team(
        name=body.name.strip(),
        scenario_slug=body.scenario_slug,
        scenario_version=body.scenario_version,
        participant_names=names or None,
        invite_code=_unique_invite(db),
    )
    db.add(team)
    db.flush()

    existing: set[int] = set()
    _add_member(db, team.id, int(owner.id), existing)
    for raw in body.member_usernames:
        member = _resolve_username(db, raw)
        _add_member(db, team.id, int(member.id), existing)

    repo_row: RepositorySubmission | None = None
    if (body.github_url or "").strip():
        repo_row = _upsert_team_repo(
            db,
            team=team,
            github_url=body.github_url.strip(),
            branch=body.branch,
            actor_id=instructor.id,
        )
        if os.getenv("TESTING") == "1":
            analyze_submission(db, repo_row.id)

    db.add(
        AuditEvent(
            actor_id=instructor.id,
            action="team.create",
            target_id=team.id,
            metadata_json=None,
        )
    )
    db.commit()
    db.refresh(team)
    if repo_row is not None:
        db.refresh(repo_row)
        _maybe_analyze(background, repo_row)
    return _team_detail(db, team)


@router.patch("/admin/teams/{team_id}", response_model=TeamDetailOut)
def update_team_admin(
    team_id: str,
    body: TeamUpdateRequest,
    background: BackgroundTasks,
    instructor: AuthUser = Depends(require_instructor),
    db: Session = Depends(get_db),
) -> TeamDetailOut:
    """Admin updates group details: name, scenario, member names, repo URL."""
    team = db.get(Team, team_id)
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found")

    if body.name is not None:
        team.name = body.name.strip()
    if body.scenario_slug is not None:
        team.scenario_slug = body.scenario_slug.strip() or None
    if body.scenario_version is not None:
        team.scenario_version = body.scenario_version
    if body.participant_names is not None:
        team.participant_names = _normalize_names(body.participant_names) or None

    repo_row: RepositorySubmission | None = None
    if (body.github_url or "").strip():
        repo_row = _upsert_team_repo(
            db,
            team=team,
            github_url=body.github_url.strip(),
            branch=body.branch,
            actor_id=instructor.id,
        )
        if body.analyze_now and os.getenv("TESTING") == "1":
            analyze_submission(db, repo_row.id)

    db.add(
        AuditEvent(
            actor_id=instructor.id,
            action="team.update",
            target_id=team.id,
            metadata_json=None,
        )
    )
    db.commit()
    db.refresh(team)
    if repo_row is not None:
        db.refresh(repo_row)
        if body.analyze_now:
            _maybe_analyze(background, repo_row)
    return _team_detail(db, team)


@router.put("/admin/teams/{team_id}/members", response_model=TeamDetailOut)
def set_team_members(
    team_id: str,
    body: TeamMembersRequest,
    instructor: AuthUser = Depends(require_instructor),
    db: Session = Depends(get_db),
) -> TeamDetailOut:
    """Replace team membership with the given cohort usernames."""
    team = db.get(Team, team_id)
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found")

    users = [_resolve_username(db, u) for u in body.usernames]
    for old in db.exec(select(TeamMember).where(TeamMember.team_id == team.id)).all():
        db.delete(old)
    db.flush()
    seen: set[int] = set()
    for user in users:
        _add_member(db, team.id, int(user.id), seen)

    db.add(
        AuditEvent(
            actor_id=instructor.id,
            action="team.set_members",
            target_id=team.id,
            metadata_json=None,
        )
    )
    db.commit()
    return _team_detail(db, team)


@router.delete("/admin/teams/{team_id}")
def delete_team(
    team_id: str,
    instructor: AuthUser = Depends(require_instructor),
    db: Session = Depends(get_db),
) -> Response:
    team = db.get(Team, team_id)
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found")
    for m in db.exec(select(TeamMember).where(TeamMember.team_id == team.id)).all():
        db.delete(m)
    db.add(
        AuditEvent(
            actor_id=instructor.id,
            action="team.delete",
            target_id=team.id,
            metadata_json=None,
        )
    )
    db.delete(team)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/teams/{team_id}", response_model=TeamDetailOut)
def get_team(
    team_id: str,
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TeamDetailOut:
    team = ensure_team_access(db, team_id, user)
    return _team_detail(db, team)


def _first_membership_team(db: Session, user_id: int) -> Team | None:
    membership = db.exec(select(TeamMember).where(TeamMember.user_id == user_id)).first()
    if membership is None:
        return None
    return db.get(Team, membership.team_id)


def _upsert_team_repo(
    db: Session,
    *,
    team: Team,
    github_url: str,
    branch: str | None,
    actor_id: int | None,
) -> RepositorySubmission:
    try:
        ref = parse_repo_url(github_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    settings = get_settings()
    provider = get_repository_provider(settings, ref)
    try:
        head = provider.resolve_head(ref, branch)
        sha = str(head.get("sha") or "").strip().lower()
        if not sha:
            raise FileNotFoundError("Could not resolve repository HEAD")
        if not branch and head.get("branch"):
            branch = str(head["branch"])
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    display_url = ref.display_url if ref.source == "github" else github_url.strip()
    row = db.exec(
        select(RepositorySubmission).where(RepositorySubmission.team_id == team.id)
    ).first()
    if row is None:
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
    else:
        row.github_url = display_url
        row.owner = ref.owner
        row.repo = ref.repo
        row.branch = branch
        if row.commit_sha != sha or row.index_status != RepoIndexStatus.ready.value:
            row.commit_sha = sha
            row.index_status = RepoIndexStatus.pending.value
            row.index_error = None

    db.add(
        AuditEvent(
            actor_id=actor_id,
            action="group.setup.repository",
            target_id=str(team.id),
            metadata_json=f'{{"url":"{display_url}","sha":"{sha}"}}',
        )
    )
    db.flush()
    return row


@router.post("/me/group-setup", response_model=GroupSetupOut)
def setup_my_group(
    body: GroupSetupRequest,
    background: BackgroundTasks,
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> GroupSetupOut:
    """Set group name + repo URL (HEAD resolved). Used from the exit interview page."""
    team: Team | None = None
    if body.team_id:
        team = ensure_team_access(db, body.team_id, user)
    else:
        team = _first_membership_team(db, user.id)

    created = False
    scenario = (body.scenario_slug or "").strip() or None
    if team is None:
        if not scenario:
            raise HTTPException(status_code=400, detail="scenario_slug is required when creating a group")
        team = Team(
            name=body.name.strip(),
            scenario_slug=scenario,
            scenario_version=body.scenario_version,
            invite_code=_unique_invite(db),
        )
        db.add(team)
        db.flush()
        _add_member(db, team.id, user.id, set())
        created = True
    else:
        team.name = body.name.strip()
        if scenario:
            team.scenario_slug = scenario
        if body.scenario_version is not None:
            team.scenario_version = body.scenario_version

    row = _upsert_team_repo(
        db,
        team=team,
        github_url=body.github_url,
        branch=body.branch,
        actor_id=user.id,
    )
    db.add(
        AuditEvent(
            actor_id=user.id,
            action="group.setup" if not created else "group.setup.create",
            target_id=team.id,
            metadata_json=None,
        )
    )
    db.commit()
    db.refresh(team)
    db.refresh(row)

    if body.analyze_now and row.index_status != RepoIndexStatus.ready.value:
        if os.getenv("TESTING") == "1":
            analyze_submission(db, row.id)
            db.refresh(row)
        else:
            background.add_task(analyze_submission_job, row.id)

    return GroupSetupOut(
        team=_team_detail(db, team),
        repository={
            "id": row.id,
            "team_id": row.team_id,
            "github_url": row.github_url,
            "owner": row.owner,
            "repo": row.repo,
            "branch": row.branch,
            "commit_sha": row.commit_sha,
            "index_status": row.index_status,
            "index_error": row.index_error,
            "attempt_count": row.attempt_count,
            "summary": row.summary_json,
        },
    )


@router.get("/me/teams", response_model=list[TeamOut])
def list_my_teams(
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[TeamOut]:
    if user.is_instructor:
        teams = list(db.exec(select(Team).order_by(Team.created_at.desc())).all())
        return [_team_out(t) for t in teams]
    memberships = list(db.exec(select(TeamMember).where(TeamMember.user_id == user.id)).all())
    if not memberships:
        return []
    teams = list(db.exec(select(Team).where(Team.id.in_([m.team_id for m in memberships]))).all())
    return [_team_out(t) for t in teams]


@router.get("/admin/teams", response_model=list[TeamDetailOut])
def list_all_teams(
    _: AuthUser = Depends(require_instructor),
    db: Session = Depends(get_db),
) -> list[TeamDetailOut]:
    teams = list(db.exec(select(Team).order_by(Team.created_at.desc())).all())
    return [_team_detail(db, t) for t in teams]
