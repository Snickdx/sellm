"""Auth deps bridging sellm Bearer sessions to exit-interview ACL."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status
from sqlmodel import Session, select

from app.db import get_db
from app.models.exit import Team, TeamMember
from app.storage.conversation_store import ROLE_ADMIN, User


@dataclass
class AuthUser:
    """Thin adapter over sellm User for exit/teams ACL."""

    id: int
    username: str
    role: str  # admin | tester | student
    is_admin: bool

    @property
    def display_name(self) -> str:
        return self.username

    @property
    def is_instructor(self) -> bool:
        return self.role == ROLE_ADMIN or self.is_admin


def get_current_user(request: Request) -> AuthUser:
    getter = getattr(request.app.state, "get_current_user", None)
    user: User | None = getter(request) if callable(getter) else None
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    role = getattr(user, "role", None) or (ROLE_ADMIN if getattr(user, "is_admin", False) else "student")
    return AuthUser(
        id=int(user.id),
        username=user.username,
        role=str(role),
        is_admin=bool(getattr(user, "is_admin", False) or role == ROLE_ADMIN),
    )


def require_instructor(user: AuthUser = Depends(get_current_user)) -> AuthUser:
    if not user.is_instructor:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Instructor role required")
    return user


def ensure_team_access(db: Session, team_id: str, user: AuthUser) -> Team:
    """Team members and instructors may access; others get 403."""
    team = db.get(Team, team_id)
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found")
    if user.is_instructor:
        return team
    membership = db.exec(
        select(TeamMember).where(TeamMember.team_id == team.id, TeamMember.user_id == user.id)
    ).first()
    if membership is None:
        raise HTTPException(status_code=403, detail="Not a team member")
    return team


def require_team_access(
    team_id: str,
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Team:
    return ensure_team_access(db, team_id, user)
