"""Team create / join / membership — student self-service."""

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
    member_usernames: list[str] = Field(default_factory=list)


class TeamJoinRequest(BaseModel):
    invite_code: str = Field(min_length=4, max_length=32)


class TeamMemberAddRequest(BaseModel):
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
    invite_code: str
    created_at: str | None


class TeamDetailOut(TeamOut):
    members: list[TeamMemberOut]


def _team_out(team: Team) -> TeamOut:
    return TeamOut(
        id=team.id,
        name=team.name,
        scenario_slug=team.scenario_slug,
        scenario_version=team.scenario_version,
        invite_code=team.invite_code,
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


def _resolve_usernames(db: Session, usernames: list[str]) -> list[User]:
    users: list[User] = []
    for name in usernames:
        uname = name.strip()
        if not uname:
            continue
        user = db.exec(select(User).where(User.username == uname)).first()
        if user is None:
            raise HTTPException(status_code=400, detail=f"Unknown username: {uname}")
        users.append(user)
    return users


def _unique_invite(db: Session) -> str:
    invite_code = secrets.token_hex(4).upper()
    while db.exec(select(Team).where(Team.invite_code == invite_code)).first() is not None:
        invite_code = secrets.token_hex(4).upper()
    return invite_code


def _create_team_impl(
    db: Session, body: TeamCreateRequest, actor: AuthUser, *, auto_add_creator: bool
) -> TeamDetailOut:
    team = Team(
        name=body.name.strip(),
        scenario_slug=body.scenario_slug,
        scenario_version=body.scenario_version,
        invite_code=_unique_invite(db),
    )
    db.add(team)
    db.flush()

    member_ids: set[int] = set()
    if auto_add_creator:
        db.add(TeamMember(team_id=team.id, user_id=actor.id))
        member_ids.add(actor.id)

    for user in _resolve_usernames(db, body.member_usernames):
        assert user.id is not None
        uid = int(user.id)
        if uid in member_ids:
            continue
        db.add(TeamMember(team_id=team.id, user_id=uid))
        member_ids.add(uid)

    db.add(
        AuditEvent(
            actor_id=actor.id,
            action="team.create",
            target_id=team.id,
            metadata_json=None,
        )
    )
    db.commit()
    db.refresh(team)
    return _team_detail(db, team)


@router.post("/teams", response_model=TeamDetailOut, status_code=status.HTTP_201_CREATED)
def create_team_self_service(
    body: TeamCreateRequest,
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TeamDetailOut:
    """Any signed-in student/tester/admin can create a team (creator is auto-added)."""
    return _create_team_impl(db, body, user, auto_add_creator=True)


@router.post("/admin/teams", response_model=TeamDetailOut, status_code=status.HTTP_201_CREATED)
def create_team_admin(
    body: TeamCreateRequest,
    instructor: AuthUser = Depends(require_instructor),
    db: Session = Depends(get_db),
) -> TeamDetailOut:
    """Instructor create (does not force-add instructor unless listed)."""
    return _create_team_impl(db, body, instructor, auto_add_creator=False)


@router.post("/teams/join", response_model=TeamDetailOut)
def join_team(
    body: TeamJoinRequest,
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TeamDetailOut:
    code = body.invite_code.strip().upper()
    team = db.exec(select(Team).where(Team.invite_code == code)).first()
    if team is None:
        raise HTTPException(status_code=404, detail="Invalid invite code")
    existing = db.exec(
        select(TeamMember).where(TeamMember.team_id == team.id, TeamMember.user_id == user.id)
    ).first()
    if existing is None:
        db.add(TeamMember(team_id=team.id, user_id=user.id))
        db.add(
            AuditEvent(
                actor_id=user.id,
                action="team.join",
                target_id=team.id,
                metadata_json=None,
            )
        )
        db.commit()
    return _team_detail(db, team)


@router.post("/admin/teams/{team_id}/members", response_model=TeamDetailOut)
@router.post("/teams/{team_id}/members", response_model=TeamDetailOut)
def add_team_members(
    team_id: str,
    body: TeamMemberAddRequest,
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TeamDetailOut:
    team = ensure_team_access(db, team_id, user)
    existing = {
        m.user_id for m in db.exec(select(TeamMember).where(TeamMember.team_id == team.id)).all()
    }
    for member in _resolve_usernames(db, body.usernames):
        assert member.id is not None
        uid = int(member.id)
        if uid in existing:
            continue
        db.add(TeamMember(team_id=team.id, user_id=uid))
        existing.add(uid)
    db.add(
        AuditEvent(
            actor_id=user.id,
            action="team.add_members",
            target_id=team.id,
            metadata_json=None,
        )
    )
    db.commit()
    return _team_detail(db, team)


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
