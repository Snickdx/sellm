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
from app.deps import AuthUser, require_instructor
from app.models.exit import AuditEvent, ClassStudent, GroupClaim, Team, TeamMember
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


class AdminStudentOut(BaseModel):
    id: str
    student_number: str
    display_name: str
    email: str
    status: str
    group_name: str | None = None
    account_username: str | None = None
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
