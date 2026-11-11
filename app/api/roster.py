"""Class roster + student group claim (hide student IDs from non-admins)."""

from __future__ import annotations

import csv
import io
import re
import secrets
import string
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.db import get_db
from app.deps import AuthUser, get_current_user, require_instructor
from app.models.exit import (
    AuditEvent,
    ClassStudent,
    GroupClaim,
    RepositorySubmission,
    Team,
    TeamMember,
)
from app.storage.conversation_store import ROLE_STUDENT

router = APIRouter(tags=["roster"])

_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CLASSLIST = _REPO_ROOT / "classlist.csv"
MIN_MEMBERS = 3  # self + 2 others
MAX_MEMBERS = 4  # self + 3 others


class PublicStudentOut(BaseModel):
    id: str
    display_name: str
    email: str
    status: str


class ClaimRequest(BaseModel):
    group_name: str = Field(min_length=2, max_length=80)
    member_ids: list[str] = Field(min_length=MIN_MEMBERS, max_length=MAX_MEMBERS)


class ClaimResponse(BaseModel):
    group_name: str
    username: str
    password: str
    team_id: str
    members: list[str]
    message: str


class GroupMemberOut(BaseModel):
    id: str
    display_name: str
    email: str


class MyGroupOut(BaseModel):
    team_id: str
    group_name: str
    claim_id: str | None = None
    members: list[GroupMemberOut] = Field(default_factory=list)
    participant_names: list[str] = Field(default_factory=list)
    can_edit_members: bool = False
    repository: dict | None = None


class UpdateGroupMembersRequest(BaseModel):
    member_ids: list[str] = Field(min_length=MIN_MEMBERS, max_length=MAX_MEMBERS)


class AdminStudentOut(BaseModel):
    id: str
    student_number: str
    display_name: str
    email: str
    status: str
    group_name: str | None = None
    account_username: str | None = None
    account_user_id: int | None = None
    claim_id: str | None = None
    team_id: str | None = None
    claimed_at: str | None = None


class AdminRosterSummary(BaseModel):
    total: int
    available: int
    claimed: int
    groups: int
    students: list[AdminStudentOut]


class ImportResult(BaseModel):
    created: int
    updated: int
    total: int


class AdminGroupUpdateRequest(BaseModel):
    group_name: str = Field(min_length=2, max_length=80)


class AdminGroupOut(BaseModel):
    claim_id: str
    group_name: str
    account_username: str
    account_user_id: int
    team_id: str
    member_ids: list[str]
    member_names: list[str]


class AdminPasswordResetResponse(BaseModel):
    claim_id: str
    username: str
    password: str
    message: str


def _display_name(row: ClassStudent) -> str:
    return f"{(row.first_name or '').strip()} {(row.last_name or '').strip()}".strip() or row.email


def _public_out(row: ClassStudent) -> PublicStudentOut:
    return PublicStudentOut(
        id=row.id,
        display_name=_display_name(row),
        email=(row.email or "").strip(),
        status=row.status,
    )


def _password(length: int = 12) -> str:
    alphabet = string.ascii_letters + string.digits
    for ch in "O0lI1":
        alphabet = alphabet.replace(ch, "")
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _slug_username(group_name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "", group_name.casefold())
    if len(slug) < 3:
        slug = f"group{slug}" if slug else "group"
    return slug[:20]


def _unique_invite(db: Session) -> str:
    for _ in range(20):
        code = secrets.token_urlsafe(9)
        if db.exec(select(Team).where(Team.invite_code == code)).first() is None:
            return code
    raise HTTPException(status_code=500, detail="Could not allocate invite code")


def _store(request: Request):
    store = getattr(request.app.state, "conversation_store", None)
    if store is None:
        raise HTTPException(status_code=500, detail="User store unavailable")
    return store


def _parse_classlist_csv(text: str) -> list[dict[str, str]]:
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV has no header row")
    rows: list[dict[str, str]] = []
    for raw in reader:
        number = (raw.get("ID number") or raw.get("student_number") or "").strip()
        first = (raw.get("First name") or raw.get("first_name") or "").strip()
        last = (raw.get("Last name") or raw.get("last_name") or "").strip()
        email = (raw.get("Email address") or raw.get("email") or "").strip()
        if not number:
            continue
        rows.append(
            {
                "student_number": number,
                "first_name": first,
                "last_name": last,
                "email": email,
            }
        )
    return rows


def _upsert_roster(db: Session, rows: list[dict[str, str]]) -> ImportResult:
    created = 0
    updated = 0
    for row in rows:
        existing = db.exec(
            select(ClassStudent).where(ClassStudent.student_number == row["student_number"])
        ).first()
        if existing is None:
            db.add(
                ClassStudent(
                    student_number=row["student_number"],
                    first_name=row["first_name"],
                    last_name=row["last_name"],
                    email=row["email"],
                    status="available",
                )
            )
            created += 1
        else:
            existing.first_name = row["first_name"]
            existing.last_name = row["last_name"]
            existing.email = row["email"]
            db.add(existing)
            updated += 1
    db.commit()
    total = len(list(db.exec(select(ClassStudent)).all()))
    return ImportResult(created=created, updated=updated, total=total)


@router.get("/roster/search", response_model=list[PublicStudentOut])
def search_roster(
    q: str = "",
    available_only: bool = True,
    db: Session = Depends(get_db),
) -> list[PublicStudentOut]:
    """Student-facing search. Never includes student_number / ID."""
    needle = " ".join((q or "").split()).strip().casefold()
    rows = list(db.exec(select(ClassStudent).order_by(ClassStudent.last_name, ClassStudent.first_name)).all())
    out: list[PublicStudentOut] = []
    for row in rows:
        if available_only and row.status != "available":
            continue
        hay = " ".join(
            [
                row.first_name or "",
                row.last_name or "",
                row.email or "",
                _display_name(row),
            ]
        ).casefold()
        # Never match on student_number in the public search path.
        if needle and needle not in hay:
            continue
        out.append(_public_out(row))
        if len(out) >= 25:
            break
    return out


@router.post("/roster/claim", response_model=ClaimResponse)
def claim_group(
    body: ClaimRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> ClaimResponse:
    """Form a group (3–4 classmates), create shared login, bind members to a team."""
    group_name = " ".join(body.group_name.split()).strip()
    if len(group_name) < 2:
        raise HTTPException(status_code=400, detail="Group name is required")

    member_ids = list(dict.fromkeys(body.member_ids))
    if len(member_ids) < MIN_MEMBERS or len(member_ids) > MAX_MEMBERS:
        raise HTTPException(
            status_code=400,
            detail=f"Select {MIN_MEMBERS}–{MAX_MEMBERS} students (you + 2 or 3 others)",
        )

    members = list(db.exec(select(ClassStudent).where(ClassStudent.id.in_(member_ids))).all())  # type: ignore[attr-defined]
    if len(members) != len(member_ids):
        raise HTTPException(status_code=400, detail="One or more selected students were not found")
    taken = [m for m in members if m.status != "available"]
    if taken:
        names = ", ".join(_display_name(m) for m in taken)
        raise HTTPException(status_code=409, detail=f"Already claimed: {names}")

    name_clash = db.exec(select(GroupClaim).where(GroupClaim.name == group_name)).first()
    if name_clash is not None:
        raise HTTPException(status_code=409, detail="That group name is already taken")

    store = _store(request)
    known = {u.username for u in store.list_users()}
    base = _slug_username(group_name)
    username = base
    n = 2
    while username in known:
        username = f"{base}{n}"
        n += 1
        if n > 99:
            raise HTTPException(status_code=500, detail="Could not allocate username")

    password = _password()
    try:
        user = store.create_user(
            username,
            password,
            role=ROLE_STUDENT,
            group_name=group_name,
            reset_usage=True,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    member_names = [_display_name(m) for m in sorted(members, key=lambda r: (_display_name(r).casefold()))]
    team = Team(
        name=group_name,
        scenario_slug="library",
        participant_names=member_names,
        invite_code=_unique_invite(db),
    )
    db.add(team)
    db.flush()
    db.add(TeamMember(team_id=team.id, user_id=int(user.id)))

    claim = GroupClaim(
        name=group_name,
        team_id=team.id,
        account_user_id=int(user.id),
        account_username=username,
        member_ids=[m.id for m in members],
        member_names=member_names,
    )
    db.add(claim)
    db.flush()

    for m in members:
        m.status = "claimed"
        m.group_claim_id = claim.id
        db.add(m)

    db.add(
        AuditEvent(
            actor_id=int(user.id),
            action="roster.claim",
            target_id=claim.id,
            metadata_json=None,
        )
    )
    db.commit()

    return ClaimResponse(
        group_name=group_name,
        username=username,
        password=password,
        team_id=team.id,
        members=member_names,
        message="Save these credentials now. The password is shown only once.",
    )


def _first_team_for_user(db: Session, user_id: int) -> Team | None:
    membership = db.exec(select(TeamMember).where(TeamMember.user_id == user_id)).first()
    if membership is None:
        return None
    return db.get(Team, membership.team_id)


def _claim_for_team(db: Session, team_id: str, user_id: int) -> GroupClaim | None:
    claim = db.exec(select(GroupClaim).where(GroupClaim.team_id == team_id)).first()
    if claim is not None:
        return claim
    return db.exec(select(GroupClaim).where(GroupClaim.account_user_id == user_id)).first()


def _latest_repo(db: Session, team_id: str) -> RepositorySubmission | None:
    return db.exec(
        select(RepositorySubmission)
        .where(RepositorySubmission.team_id == team_id)
        .order_by(RepositorySubmission.updated_at.desc())
    ).first()


def _repo_payload(row: RepositorySubmission | None) -> dict | None:
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


def _members_out(db: Session, member_ids: list[str]) -> list[GroupMemberOut]:
    if not member_ids:
        return []
    rows = list(db.exec(select(ClassStudent).where(ClassStudent.id.in_(member_ids))).all())  # type: ignore[attr-defined]
    by_id = {r.id: r for r in rows}
    out: list[GroupMemberOut] = []
    for mid in member_ids:
        row = by_id.get(mid)
        if row is None:
            continue
        out.append(
            GroupMemberOut(
                id=row.id,
                display_name=_display_name(row),
                email=(row.email or "").strip(),
            )
        )
    return out


def _my_group_out(db: Session, team: Team, claim: GroupClaim | None) -> MyGroupOut:
    if claim is not None:
        members = _members_out(db, list(claim.member_ids or []))
        names = list(claim.member_names or []) or [m.display_name for m in members]
    else:
        members = []
        names = list(team.participant_names or [])
    return MyGroupOut(
        team_id=team.id,
        group_name=team.name,
        claim_id=claim.id if claim else None,
        members=members,
        participant_names=names,
        can_edit_members=claim is not None,
        repository=_repo_payload(_latest_repo(db, team.id)),
    )


@router.get("/me/group", response_model=MyGroupOut)
def get_my_group(
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MyGroupOut:
    """Current student's group, roster members (if claimed), and repository."""
    team = _first_team_for_user(db, user.id)
    if team is None:
        raise HTTPException(status_code=404, detail="No group yet — claim classmates from the landing page")
    claim = _claim_for_team(db, team.id, user.id)
    return _my_group_out(db, team, claim)


@router.put("/me/group/members", response_model=MyGroupOut)
def update_my_group_members(
    body: UpdateGroupMembersRequest,
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MyGroupOut:
    """Replace group roster members using available (ungrouped) classmates plus current members."""
    team = _first_team_for_user(db, user.id)
    if team is None:
        raise HTTPException(status_code=404, detail="No group yet — claim classmates from the landing page")
    claim = _claim_for_team(db, team.id, user.id)
    if claim is None:
        raise HTTPException(
            status_code=400,
            detail="This group was not formed from the class roster, so members cannot be edited here",
        )

    member_ids = list(dict.fromkeys(body.member_ids))
    if len(member_ids) < MIN_MEMBERS or len(member_ids) > MAX_MEMBERS:
        raise HTTPException(
            status_code=400,
            detail=f"Select {MIN_MEMBERS}–{MAX_MEMBERS} students (you + 2 or 3 others)",
        )

    members = list(db.exec(select(ClassStudent).where(ClassStudent.id.in_(member_ids))).all())  # type: ignore[attr-defined]
    if len(members) != len(member_ids):
        raise HTTPException(status_code=400, detail="One or more selected students were not found")

    current_ids = set(claim.member_ids or [])
    blocked = [
        m
        for m in members
        if m.id not in current_ids and (m.status != "available" or m.group_claim_id not in (None, ""))
    ]
    if blocked:
        names = ", ".join(_display_name(m) for m in blocked)
        raise HTTPException(status_code=409, detail=f"Already in another group: {names}")

    old_rows = list(
        db.exec(select(ClassStudent).where(ClassStudent.id.in_(list(current_ids)))).all()  # type: ignore[attr-defined]
    )
    keep = set(member_ids)
    for row in old_rows:
        if row.id in keep:
            continue
        row.status = "available"
        row.group_claim_id = None
        db.add(row)

    member_names = [
        _display_name(m) for m in sorted(members, key=lambda r: (_display_name(r).casefold()))
    ]
    for m in members:
        m.status = "claimed"
        m.group_claim_id = claim.id
        db.add(m)

    claim.member_ids = member_ids
    claim.member_names = member_names
    db.add(claim)
    team.participant_names = member_names
    db.add(team)
    db.add(
        AuditEvent(
            actor_id=user.id,
            action="roster.update_members",
            target_id=claim.id,
            metadata_json=None,
        )
    )
    db.commit()
    db.refresh(team)
    db.refresh(claim)
    return _my_group_out(db, team, claim)


def _admin_group_out(claim: GroupClaim) -> AdminGroupOut:
    return AdminGroupOut(
        claim_id=claim.id,
        group_name=claim.name,
        account_username=claim.account_username,
        account_user_id=int(claim.account_user_id),
        team_id=claim.team_id,
        member_ids=list(claim.member_ids or []),
        member_names=list(claim.member_names or []),
    )


def _require_claim(db: Session, claim_id: str) -> GroupClaim:
    claim = db.get(GroupClaim, claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail="Group not found")
    return claim


def _release_claim_members(db: Session, claim: GroupClaim) -> None:
    rows = list(
        db.exec(select(ClassStudent).where(ClassStudent.group_claim_id == claim.id)).all()
    )
    for row in rows:
        row.status = "available"
        row.group_claim_id = None
        db.add(row)


@router.get("/admin/roster", response_model=AdminRosterSummary)
def admin_roster(
    _: AuthUser = Depends(require_instructor),
    db: Session = Depends(get_db),
) -> AdminRosterSummary:
    students = list(
        db.exec(select(ClassStudent).order_by(ClassStudent.last_name, ClassStudent.first_name)).all()
    )
    claims = {c.id: c for c in db.exec(select(GroupClaim)).all()}
    out: list[AdminStudentOut] = []
    for row in students:
        claim = claims.get(row.group_claim_id or "")
        out.append(
            AdminStudentOut(
                id=row.id,
                student_number=row.student_number,
                display_name=_display_name(row),
                email=row.email,
                status=row.status,
                group_name=claim.name if claim else None,
                account_username=claim.account_username if claim else None,
                account_user_id=int(claim.account_user_id) if claim else None,
                claim_id=claim.id if claim else None,
                team_id=claim.team_id if claim else None,
                claimed_at=claim.created_at.isoformat() if claim and claim.created_at else None,
            )
        )
    available = sum(1 for s in students if s.status == "available")
    claimed = sum(1 for s in students if s.status == "claimed")
    return AdminRosterSummary(
        total=len(students),
        available=available,
        claimed=claimed,
        groups=len(claims),
        students=out,
    )


@router.patch("/admin/roster/groups/{claim_id}", response_model=AdminGroupOut)
def admin_rename_group(
    claim_id: str,
    body: AdminGroupUpdateRequest,
    request: Request,
    instructor: AuthUser = Depends(require_instructor),
    db: Session = Depends(get_db),
) -> AdminGroupOut:
    """Rename a claimed student group (claim + team + account group_name)."""
    claim = _require_claim(db, claim_id)
    group_name = " ".join(body.group_name.split()).strip()
    if len(group_name) < 2:
        raise HTTPException(status_code=400, detail="Group name is required")

    clash = db.exec(
        select(GroupClaim).where(GroupClaim.name == group_name, GroupClaim.id != claim.id)
    ).first()
    if clash is not None:
        raise HTTPException(status_code=409, detail="That group name is already taken")

    claim.name = group_name
    db.add(claim)
    team = db.get(Team, claim.team_id)
    if team is not None:
        team.name = group_name
        db.add(team)

    store = _store(request)
    store.update_user(int(claim.account_user_id), group_name=group_name)

    db.add(
        AuditEvent(
            actor_id=instructor.id,
            action="roster.rename_group",
            target_id=claim.id,
            metadata_json=None,
        )
    )
    db.commit()
    db.refresh(claim)
    return _admin_group_out(claim)


@router.delete("/admin/roster/groups/{claim_id}", response_model=AdminGroupOut)
def admin_delete_group(
    claim_id: str,
    request: Request,
    instructor: AuthUser = Depends(require_instructor),
    db: Session = Depends(get_db),
) -> AdminGroupOut:
    """Release roster members and remove the claim. Keeps the shared login account."""
    claim = _require_claim(db, claim_id)
    out = _admin_group_out(claim)
    _release_claim_members(db, claim)

    for m in db.exec(select(TeamMember).where(TeamMember.team_id == claim.team_id)).all():
        db.delete(m)

    store = _store(request)
    store.update_user(int(claim.account_user_id), clear_group=True)

    db.add(
        AuditEvent(
            actor_id=instructor.id,
            action="roster.delete_group",
            target_id=claim.id,
            metadata_json=None,
        )
    )
    db.delete(claim)
    db.commit()
    return out


@router.post(
    "/admin/roster/groups/{claim_id}/reset-password",
    response_model=AdminPasswordResetResponse,
)
def admin_reset_group_password(
    claim_id: str,
    request: Request,
    instructor: AuthUser = Depends(require_instructor),
    db: Session = Depends(get_db),
) -> AdminPasswordResetResponse:
    """Generate a new password for the group's shared login (shown once)."""
    claim = _require_claim(db, claim_id)
    password = _password()
    store = _store(request)
    updated = store.update_user(int(claim.account_user_id), password=password)
    if updated is None:
        raise HTTPException(status_code=404, detail="Group account not found")

    db.add(
        AuditEvent(
            actor_id=instructor.id,
            action="roster.reset_password",
            target_id=claim.id,
            metadata_json=None,
        )
    )
    db.commit()
    return AdminPasswordResetResponse(
        claim_id=claim.id,
        username=claim.account_username,
        password=password,
        message="Save this password now. It is shown only once.",
    )


def _finish_import(db: Session, instructor: AuthUser, raw: str) -> ImportResult:
    rows = _parse_classlist_csv(raw)
    if not rows:
        raise HTTPException(status_code=400, detail="No students found in CSV")
    result = _upsert_roster(db, rows)
    db.add(
        AuditEvent(
            actor_id=instructor.id,
            action="roster.import",
            target_id=None,
            metadata_json=f'{{"created":{result.created},"updated":{result.updated}}}',
        )
    )
    db.commit()
    return result


@router.post("/admin/roster/import", response_model=ImportResult)
def admin_import_roster_default(
    instructor: AuthUser = Depends(require_instructor),
    db: Session = Depends(get_db),
) -> ImportResult:
    """Import/refresh from repo-root classlist.csv."""
    path = DEFAULT_CLASSLIST
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"Missing {path.name}")
    return _finish_import(db, instructor, path.read_text(encoding="utf-8-sig"))


@router.post("/admin/roster/import-upload", response_model=ImportResult)
async def admin_import_roster_upload(
    instructor: AuthUser = Depends(require_instructor),
    db: Session = Depends(get_db),
    file: UploadFile = File(...),
) -> ImportResult:
    """Import/refresh from an uploaded CSV."""
    raw = (await file.read()).decode("utf-8-sig")
    return _finish_import(db, instructor, raw)
