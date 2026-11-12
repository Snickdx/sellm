"""Teams — admin assigns a cohort credential; students fill group details."""

from __future__ import annotations

import os
import secrets

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import Session, select

from app.db import get_db
from app.deps import AuthUser, ensure_team_access, get_current_user, require_instructor
from app.models.exit import (
    AuditEvent,
    ClassStudent,
    GroupClaim,
    RepoIndexStatus,
    RepositorySubmission,
    Team,
    TeamMember,
)
from app.providers.github import get_repository_provider, parse_repo_url
from app.repo.ingest import analyze_submission, analyze_submission_job
from app.settings import get_settings
from app.storage.conversation_store import User

router = APIRouter(tags=["teams"])


class TeamCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    scenario_slug: str | None = None
    scenario_version: str | None = None
    # Cohort username that owns/shares this team login (required for admin create).
    owner_username: str | None = None
    member_usernames: list[str] = Field(default_factory=list)
    # Class-list student ids (preferred). Names are derived from the roster.
    roster_member_ids: list[str] = Field(default_factory=list)
    # Legacy free-text names — ignored when roster_member_ids is provided.
    participant_names: list[str] = Field(default_factory=list)
    github_url: str | None = Field(default=None, max_length=500)
    branch: str | None = Field(default=None, max_length=200)


class TeamUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    scenario_slug: str | None = None
    scenario_version: str | None = None
    roster_member_ids: list[str] | None = None
    # Legacy free-text names — ignored when roster_member_ids is provided.
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


class RosterMemberOut(BaseModel):
    id: str
    display_name: str
    email: str = ""


class TeamOut(BaseModel):
    id: str
    name: str
    scenario_slug: str | None
    scenario_version: str | None
    roster_member_ids: list[str] = Field(default_factory=list)
    participant_names: list[str] = Field(default_factory=list)
    created_at: str | None


class TeamDetailOut(TeamOut):
    members: list[TeamMemberOut]
    roster_members: list[RosterMemberOut] = Field(default_factory=list)
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


def _display_name(row: ClassStudent) -> str:
    return f"{(row.first_name or '').strip()} {(row.last_name or '').strip()}".strip() or row.email


def _normalize_roster_ids(ids: list[str] | None) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in ids or []:
        mid = str(raw or "").strip()
        if not mid or mid in seen:
            continue
        seen.add(mid)
        cleaned.append(mid)
    return cleaned


def _resolve_roster_members(db: Session, ids: list[str]) -> list[ClassStudent]:
    member_ids = _normalize_roster_ids(ids)
    if not member_ids:
        return []
    rows = list(db.exec(select(ClassStudent).where(ClassStudent.id.in_(member_ids))).all())  # type: ignore[attr-defined]
    by_id = {row.id: row for row in rows}
    missing = [mid for mid in member_ids if mid not in by_id]
    if missing:
        raise HTTPException(status_code=400, detail="One or more class-list students were not found")
    return [by_id[mid] for mid in member_ids]


def _apply_roster_members(db: Session, team: Team, members: list[ClassStudent]) -> None:
    """Persist class-list members on the team and keep any linked GroupClaim in sync."""
    ordered = sorted(members, key=lambda row: _display_name(row).casefold())
    member_ids = [row.id for row in ordered]
    member_names = [_display_name(row) for row in ordered]
    team.roster_member_ids = member_ids or None
    team.participant_names = member_names or None
    flag_modified(team, "roster_member_ids")
    flag_modified(team, "participant_names")
    db.add(team)

    claim = db.exec(select(GroupClaim).where(GroupClaim.team_id == team.id)).first()
    if claim is None:
        return

    old_ids = set(_normalize_roster_ids(list(claim.member_ids or [])))
    new_ids = set(member_ids)

    for mid in old_ids - new_ids:
        row = db.get(ClassStudent, mid)
        if row is None:
            continue
        if row.group_claim_id == claim.id:
            row.status = "available"
            row.group_claim_id = None
            db.add(row)

    for mid in new_ids - old_ids:
        row = db.get(ClassStudent, mid)
        if row is None:
            continue
        other = (row.group_claim_id or "").strip()
        if other and other != claim.id:
            raise HTTPException(
                status_code=409,
                detail=f"{_display_name(row)} is already in another group",
            )
        row.status = "claimed"
        row.group_claim_id = claim.id
        db.add(row)

    claim.member_ids = member_ids
    claim.member_names = member_names
    flag_modified(claim, "member_ids")
    flag_modified(claim, "member_names")
    db.add(claim)


def _roster_ids_for_team(db: Session, team: Team) -> list[str]:
    stored = _normalize_roster_ids(list(team.roster_member_ids or []))
    if stored:
        return stored
    claim = db.exec(select(GroupClaim).where(GroupClaim.team_id == team.id)).first()
    if claim is not None:
        return _normalize_roster_ids(list(claim.member_ids or []))
    return []


def _roster_members_out(db: Session, team: Team) -> list[RosterMemberOut]:
    ids = _roster_ids_for_team(db, team)
    if ids:
        rows = list(db.exec(select(ClassStudent).where(ClassStudent.id.in_(ids))).all())  # type: ignore[attr-defined]
        by_id = {row.id: row for row in rows}
        out: list[RosterMemberOut] = []
        for mid in ids:
            row = by_id.get(mid)
            if row is None:
                continue
            out.append(
                RosterMemberOut(
                    id=row.id,
                    display_name=_display_name(row),
                    email=(row.email or "").strip(),
                )
            )
        return out

    # Legacy teams: match free-text participant_names back to the class list.
    names = _normalize_names(list(team.participant_names or []))
    if not names:
        return []
    wanted = {name.casefold(): name for name in names}
    matched: dict[str, ClassStudent] = {}
    for row in db.exec(select(ClassStudent)).all():
        key = _display_name(row).casefold()
        if key in wanted and key not in matched:
            matched[key] = row
    return [
        RosterMemberOut(
            id=matched[name.casefold()].id,
            display_name=_display_name(matched[name.casefold()]),
            email=(matched[name.casefold()].email or "").strip(),
        )
        if name.casefold() in matched
        else RosterMemberOut(id="", display_name=name, email="")
        for name in names
        if name.casefold() in matched
    ]


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
        roster_member_ids=list(team.roster_member_ids or []),
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
    roster_members = _roster_members_out(db, team)
    if not base.roster_member_ids and roster_members:
        base.roster_member_ids = [m.id for m in roster_members if m.id]
    if not base.participant_names and roster_members:
        base.participant_names = [m.display_name for m in roster_members]
    return TeamDetailOut(
        **base.model_dump(),
        members=members,
        roster_members=roster_members,
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
    """Admin creates a team: cohort owner, scenario, repo, and class-list members."""
    owner_name = (body.owner_username or "").strip()
    if not owner_name:
        raise HTTPException(
            status_code=400,
            detail="owner_username is required — pick the cohort login that shares this team",
        )
    owner = _resolve_username(db, owner_name)

    team = Team(
        name=body.name.strip(),
        scenario_slug=body.scenario_slug,
        scenario_version=body.scenario_version,
        invite_code=_unique_invite(db),
    )
    db.add(team)
    db.flush()
    if body.roster_member_ids:
        _apply_roster_members(db, team, _resolve_roster_members(db, body.roster_member_ids))
    else:
        names = _normalize_names(body.participant_names)
        team.participant_names = names or None
        flag_modified(team, "participant_names")
        db.add(team)

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
    """Admin updates group details: name, scenario, class-list members, repo URL."""
    team = db.get(Team, team_id)
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found")

    if body.name is not None:
        team.name = body.name.strip()
    if body.scenario_slug is not None:
        team.scenario_slug = body.scenario_slug.strip() or None
    if body.scenario_version is not None:
        team.scenario_version = body.scenario_version
    if body.roster_member_ids is not None:
        _apply_roster_members(db, team, _resolve_roster_members(db, body.roster_member_ids))
    elif body.participant_names is not None:
        team.participant_names = _normalize_names(body.participant_names) or None
        team.roster_member_ids = None
        flag_modified(team, "participant_names")
        flag_modified(team, "roster_member_ids")
        db.add(team)

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

    db.add(team)
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
