"""Teams — admin assigns a cohort credential as the shared login owner."""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.seproject.db import get_db
from app.seproject.deps import AuthUser, ensure_team_access, get_current_user, require_instructor
from app.seproject.exit_models import AuditEvent, Team, TeamMember
from app.storage.conversation_store import User

router = APIRouter(tags=["teams"])


class TeamCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    scenario_slug: str | None = None
    scenario_version: str | None = None
    # Cohort username that owns/shares this team login (required for admin create).
    owner_username: str | None = None
    member_usernames: list[str] = Field(default_factory=list)


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
    created_at: str | None


class TeamDetailOut(TeamOut):
    members: list[TeamMemberOut]


def _team_out(team: Team) -> TeamOut:
    return TeamOut(
        id=team.id,
        name=team.name,
        scenario_slug=team.scenario_slug,
        scenario_version=team.scenario_version,
        created_at=team.created_at.isoformat() if team.created_at else None,
    )


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
    return TeamDetailOut(**base.model_dump(), members=members)


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


@router.post("/admin/teams", response_model=TeamDetailOut, status_code=status.HTTP_201_CREATED)
def create_team_admin(
    body: TeamCreateRequest,
    instructor: AuthUser = Depends(require_instructor),
    db: Session = Depends(get_db),
) -> TeamDetailOut:
    """Admin creates a team and assigns it to a cohort credential (owner_username)."""
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

    existing: set[int] = set()
    _add_member(db, team.id, int(owner.id), existing)
    for raw in body.member_usernames:
        member = _resolve_username(db, raw)
        _add_member(db, team.id, int(member.id), existing)

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


@router.delete("/admin/teams/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_team(
    team_id: str,
    instructor: AuthUser = Depends(require_instructor),
    db: Session = Depends(get_db),
) -> None:
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


@router.get("/teams/{team_id}", response_model=TeamDetailOut)
def get_team(
    team_id: str,
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TeamDetailOut:
    team = ensure_team_access(db, team_id, user)
    return _team_detail(db, team)


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
