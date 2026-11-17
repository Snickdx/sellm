"""Server-rendered HTML pages (cookie session + Jinja)."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select

from app.db import configure_engine, get_engine
from app.models.exit import ExitInterviewSession, GroupClaim, Team, TeamMember
from app.ops.policy import policy_document
from app.settings import get_settings
from app.storage.conversation_store import ROLE_ADMIN, normalize_role
from app.web.session_cookie import clear_session_cookie, set_session_cookie

router = APIRouter(tags=["pages"])

ADMIN_VIEW_REDIRECTS = {
    "users": "/admin/users",
    "roster": "/admin/roster",
    "teams": "/admin/teams",
    "tokens": "/admin/tokens",
    "appkeys": "/admin/app-keys",
    "defaults": "/admin/defaults",
}


def _templates(request: Request):
    return request.app.state.templates


def _render(request: Request, name: str, context: Optional[dict[str, Any]] = None):
    render = getattr(request.app.state, "render_template", None)
    if callable(render):
        return render(request, name, context)
    # Fallback if wired only via templates
    ctx = dict(context or {})
    ctx["request"] = request
    return _templates(request).TemplateResponse(request, name, ctx)


def _store(request: Request):
    return request.app.state.conversation_store


def _db_engine(request: Request):
    store = _store(request)
    engine = getattr(store, "engine", None)
    if engine is not None:
        try:
            configure_engine(engine)
        except Exception:
            pass
        return engine
    return get_engine()


def _user(request: Request):
    getter = getattr(request.app.state, "get_current_user", None)
    return getter(request) if callable(getter) else None


def _role(user) -> str:
    return normalize_role(getattr(user, "role", None), is_admin=bool(getattr(user, "is_admin", False)))


def _is_admin(user) -> bool:
    if not user:
        return False
    return _role(user) == ROLE_ADMIN or bool(getattr(user, "is_admin", False))


def _base_ctx(request: Request, page: str, **extra: Any) -> dict[str, Any]:
    user = _user(request)
    ctx = {
        "page": page,
        "user": user,
        "is_admin": _is_admin(user),
        "flash": request.query_params.get("ok"),
        "error": request.query_params.get("error"),
    }
    ctx.update(extra)
    return ctx


def _require_user(request: Request):
    user = _user(request)
    if not user:
        return None, RedirectResponse(url="/", status_code=303)
    return user, None


def _require_admin_page(request: Request):
    user = _user(request)
    if not user:
        return None, RedirectResponse(url="/admin/login", status_code=303)
    if not _is_admin(user):
        return None, _render(request, "admin/deny.html", _base_ctx(request, "admin_deny"))
    return user, None


def _login_user(request: Request, username: str, password: str):
    store = _store(request)
    user = store.get_user_by_credentials(username, password)
    if not user:
        return None, None
    token = store.create_session(user.id)
    return user, token


# ── Auth form posts ───────────────────────────────────────────


@router.post("/login")
async def html_login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next: str = Form("/group"),
):
    user, token = _login_user(request, username.strip(), password)
    if not user or not token:
        return _render(
            request,
            "landing.html",
            _base_ctx(request, "landing", error="Invalid username or password"),
        )
    dest = next if next.startswith("/") else "/group"
    if _is_admin(user) and dest == "/group":
        # stay on student default
        pass
    response = RedirectResponse(url=dest, status_code=303)
    set_session_cookie(response, token)
    return response


@router.post("/logout")
@router.get("/logout")
async def html_logout(request: Request):
    token = None
    from app.services.auth_service import AuthService

    token = AuthService.token_from_request(request)
    if token:
        _store(request).delete_session(token)
    response = RedirectResponse(url="/", status_code=303)
    clear_session_cookie(response)
    return response


@router.get("/admin/login")
async def admin_login_get(request: Request):
    user = _user(request)
    if user and _is_admin(user):
        return RedirectResponse(url="/admin/users", status_code=303)
    return _render(request, "admin/login.html", _base_ctx(request, "admin_login"))


@router.post("/admin/login")
async def admin_login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    user, token = _login_user(request, username.strip(), password)
    if not user or not token:
        return _render(
            request,
            "admin/login.html",
            _base_ctx(request, "admin_login", error="Invalid username or password"),
        )
    if not _is_admin(user):
        response = _render(
            request,
            "admin/deny.html",
            _base_ctx(request, "admin_deny", user=user, is_admin=False),
        )
        set_session_cookie(response, token)
        return response
    response = RedirectResponse(url="/admin/users", status_code=303)
    set_session_cookie(response, token)
    return response


# ── Student pages ─────────────────────────────────────────────


@router.get("/")
@router.get("/login")
@router.get("/claim")
async def landing(request: Request):
    user = _user(request)
    if user:
        return RedirectResponse(url="/group", status_code=303)
    return _render(request, "landing.html", _base_ctx(request, "landing"))


def _list_scenarios() -> list[dict]:
    from app.scenarios.registry import scenario_registry

    out: list[dict] = []
    try:
        for row in scenario_registry.list_student_safe():
            slug = row.get("slug") if isinstance(row, dict) else getattr(row, "slug", None)
            title = (
                row.get("title")
                if isinstance(row, dict)
                else getattr(row, "title", None)
            ) or slug
            if slug:
                out.append({"slug": slug, "title": title})
    except Exception:
        out = []
    return out or [{"slug": "library", "title": "library"}]


def _auth_user(user):
    from app.deps import AuthUser

    return AuthUser(
        id=int(user.id),
        username=user.username,
        role=_role(user),
        is_admin=_is_admin(user),
    )


@router.get("/group")
async def group_page(request: Request):
    user, redirect = _require_user(request)
    if redirect:
        return redirect
    group = None
    scenarios = _list_scenarios()
    with Session(_db_engine(request)) as db:
        membership = db.exec(select(TeamMember).where(TeamMember.user_id == int(user.id))).first()
        if membership:
            team = db.get(Team, membership.team_id)
            if team:
                from app.api.roster import _claim_for_team, _my_group_out

                claim = _claim_for_team(db, team.id, int(user.id))
                group = _my_group_out(db, team, claim, login_username=user.username)

    return _render(
        request,
        "group.html",
        _base_ctx(
            request,
            "group",
            group=group,
            scenarios=scenarios,
            new_password=request.query_params.get("password"),
        ),
    )


@router.post("/group/reset-password")
async def group_reset_password(request: Request):
    user, redirect = _require_user(request)
    if redirect:
        return redirect
    from app.api.roster import reset_my_group_password

    auth = _auth_user(user)
    with Session(_db_engine(request)) as db:
        try:
            result = reset_my_group_password(request, auth, db)
        except HTTPException as exc:
            return RedirectResponse(url=f"/group?error={exc.detail}", status_code=303)
    return RedirectResponse(
        url=f"/group?ok=Password+reset&password={result.password}",
        status_code=303,
    )


@router.post("/group/setup")
async def group_setup(
    request: Request,
    background: BackgroundTasks,
    group_name: str = Form(...),
    scenario_slug: str = Form(...),
    github_url: str = Form(...),
):
    user, redirect = _require_user(request)
    if redirect:
        return redirect
    from app.api.teams import GroupSetupRequest, setup_my_group

    auth = _auth_user(user)
    body = GroupSetupRequest(
        name=group_name.strip(),
        github_url=github_url.strip(),
        scenario_slug=scenario_slug.strip() or None,
        analyze_now=True,
    )
    with Session(_db_engine(request)) as db:
        try:
            setup_my_group(body, background, auth, db)
        except HTTPException as exc:
            return RedirectResponse(url=f"/group?error={exc.detail}", status_code=303)
        except Exception as exc:
            return RedirectResponse(url=f"/group?error={exc}", status_code=303)
    return RedirectResponse(url="/group?ok=Saved", status_code=303)


@router.get("/req")
async def req_page(request: Request):
    user, redirect = _require_user(request)
    if redirect:
        return redirect
    store = _store(request)
    convos = store.list_conversations_for_user(int(user.id))
    conversations = [
        {
            "id": c.id,
            "title": c.title,
            "scenario_slug": getattr(c, "scenario_slug", None),
            "updated_at": c.updated_at.isoformat() if getattr(c, "updated_at", None) else None,
        }
        for c in convos
    ]
    return _render(
        request,
        "req.html",
        _base_ctx(request, "req", conversations=conversations),
    )


@router.get("/policy")
async def policy_page(request: Request):
    user, redirect = _require_user(request)
    if redirect:
        return redirect
    return _render(
        request,
        "policy.html",
        _base_ctx(request, "policy", policy=policy_document(get_settings())),
    )


@router.get("/exit")
async def exit_hub(request: Request):
    user, redirect = _require_user(request)
    if redirect:
        return redirect
    teams = []
    team_id = None
    sessions = []
    interviewee_names: list[str] = []
    with Session(_db_engine(request)) as db:
        memberships = list(db.exec(select(TeamMember).where(TeamMember.user_id == int(user.id))).all())
        for m in memberships:
            team = db.get(Team, m.team_id)
            if team:
                teams.append({"id": team.id, "name": team.name})
        if teams:
            team_id = teams[0]["id"]
            team = db.get(Team, team_id)
            if team:
                interviewee_names = list(team.participant_names or [])
                claim = db.exec(select(GroupClaim).where(GroupClaim.team_id == team.id)).first()
                if claim and claim.member_names:
                    interviewee_names = list(claim.member_names)
            rows = list(
                db.exec(
                    select(ExitInterviewSession)
                    .where(ExitInterviewSession.team_id == team_id)
                    .order_by(ExitInterviewSession.created_at.desc())
                ).all()
            )
            sessions = [
                {
                    "id": r.id,
                    "status": r.status,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "participant_names": [],
                }
                for r in rows
            ]
    return _render(
        request,
        "exit.html",
        _base_ctx(
            request,
            "exit",
            teams=teams,
            team_id=team_id,
            sessions=sessions,
            interviewee_names=interviewee_names,
            policy=policy_document(get_settings()),
        ),
    )


@router.get("/teams/{team_id}/exit")
async def exit_team_page(request: Request, team_id: str):
    user, redirect = _require_user(request)
    if redirect:
        return redirect
    session_id = request.query_params.get("session")
    teams = []
    sessions = []
    interviewee_names: list[str] = []
    session = None
    with Session(_db_engine(request)) as db:
        from app.deps import AuthUser, ensure_team_access

        auth = AuthUser(
            id=int(user.id),
            username=user.username,
            role=_role(user),
            is_admin=_is_admin(user),
        )
        try:
            team = ensure_team_access(db, team_id, auth)
        except HTTPException:
            return RedirectResponse(url="/exit", status_code=303)
        memberships = list(db.exec(select(TeamMember).where(TeamMember.user_id == int(user.id))).all())
        for m in memberships:
            t = db.get(Team, m.team_id)
            if t:
                teams.append({"id": t.id, "name": t.name})
        interviewee_names = list(team.participant_names or [])
        claim = db.exec(select(GroupClaim).where(GroupClaim.team_id == team.id)).first()
        if claim and claim.member_names:
            interviewee_names = list(claim.member_names)
        rows = list(
            db.exec(
                select(ExitInterviewSession)
                .where(ExitInterviewSession.team_id == team_id)
                .order_by(ExitInterviewSession.created_at.desc())
            ).all()
        )
        sessions = [
            {
                "id": r.id,
                "status": r.status,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "participant_names": [],
            }
            for r in rows
        ]
        if session_id:
            session = db.get(ExitInterviewSession, session_id)
            if session and session.team_id != team_id:
                session = None

    if session_id:
        return _render(
            request,
            "exit_session.html",
            _base_ctx(request, "exit_session", team_id=team_id, session=session),
        )
    return _render(
        request,
        "exit.html",
        _base_ctx(
            request,
            "exit",
            teams=teams or [{"id": team_id, "name": team_id}],
            team_id=team_id,
            sessions=sessions,
            interviewee_names=interviewee_names,
            policy=policy_document(get_settings()),
        ),
    )


# ── Admin pages ───────────────────────────────────────────────


@router.get("/admin")
async def admin_root(request: Request):
    view = request.query_params.get("view")
    if view and view in ADMIN_VIEW_REDIRECTS:
        return RedirectResponse(url=ADMIN_VIEW_REDIRECTS[view], status_code=303)
    return RedirectResponse(url="/admin/users", status_code=303)


def _admin_user_rows(request: Request, group: Optional[str] = None):
    from app.api.admin import _claimed_group_names, _user_summary

    store = _store(request)
    settings = store.get_app_settings()
    users = store.list_users()
    claimed = _claimed_group_names()

    def resolved_group(u) -> str:
        if u.id is not None and int(u.id) in claimed:
            return claimed[int(u.id)]
        return (getattr(u, "group_name", None) or "").strip()

    if group is not None:
        needle = group.strip()
        if needle == "" or needle == "(ungrouped)":
            users = [u for u in users if not resolved_group(u)]
        else:
            users = [u for u in users if resolved_group(u) == needle]
    return [_user_summary(store, u, settings, claimed_groups=claimed) for u in users]


def _admin_workspace(request: Request, view: str):
    user, deny = _require_admin_page(request)
    if deny:
        return deny
    page = {
        "users": "admin_users",
        "roster": "admin_roster",
        "teams": "admin_teams",
        "tokens": "admin_tokens",
        "appkeys": "admin_appkeys",
        "defaults": "admin_defaults",
    }.get(view, "admin_users")
    return _render(
        request,
        "admin/workspace.html",
        _base_ctx(request, page, initial_view=view),
    )


@router.get("/admin/users")
async def admin_users(request: Request):
    return _admin_workspace(request, "users")


@router.post("/admin/users")
async def admin_users_create(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form("student"),
    group_name: str = Form(""),
    token_limit: int = Form(50000),
):
    user, deny = _require_admin_page(request)
    if deny:
        return deny
    store = _store(request)
    try:
        store.create_user(
            username.strip(),
            password,
            token_limit=token_limit,
            role=role,
            is_admin=role == ROLE_ADMIN,
            group_name=group_name.strip() or None,
            reset_usage=True,
        )
    except ValueError as exc:
        return RedirectResponse(url=f"/admin/users?error={exc}", status_code=303)
    return RedirectResponse(url="/admin/users?ok=Created", status_code=303)


@router.get("/admin/users/{user_id}")
async def admin_user_detail(request: Request, user_id: int):
    # Classic admin UX opens the user editor as a modal on /admin/users.
    return RedirectResponse(url="/admin/users", status_code=303)


@router.post("/admin/users/{user_id}")
async def admin_user_update(
    request: Request,
    user_id: int,
    username: str = Form(...),
    role: str = Form("student"),
    group_name: str = Form(""),
    token_limit: int = Form(0),
    reset_tokens: Optional[str] = Form(None),
):
    admin, deny = _require_admin_page(request)
    if deny:
        return deny
    store = _store(request)
    if int(admin.id) == int(user_id) and role != ROLE_ADMIN:
        return RedirectResponse(
            url=f"/admin/users/{user_id}?error=Cannot+remove+your+own+admin+role",
            status_code=303,
        )
    store.update_user(
        user_id,
        role=role,
        is_admin=role == ROLE_ADMIN,
        group_name=group_name.strip() or None,
        token_limit=token_limit,
        tokens_used=0 if reset_tokens else None,
    )
    # username field is display-only for now (store has no rename helper)
    _ = username
    return RedirectResponse(url=f"/admin/users/{user_id}?ok=Saved", status_code=303)


@router.post("/admin/users/{user_id}/reset-password")
async def admin_user_reset_pw(request: Request, user_id: int):
    admin, deny = _require_admin_page(request)
    if deny:
        return deny
    import secrets
    import string

    alphabet = string.ascii_letters + string.digits
    password = "".join(secrets.choice(alphabet) for _ in range(12))
    updated = _store(request).update_user(user_id, password=password)
    if not updated:
        raise HTTPException(status_code=404, detail="User not found")
    return RedirectResponse(
        url=f"/admin/users/{user_id}?ok=Password+reset&password={password}",
        status_code=303,
    )


@router.post("/admin/users/{user_id}/delete")
async def admin_user_delete(request: Request, user_id: int):
    admin, deny = _require_admin_page(request)
    if deny:
        return deny
    if int(admin.id) == int(user_id):
        return RedirectResponse(url=f"/admin/users/{user_id}?error=Cannot+delete+yourself", status_code=303)
    _store(request).delete_user(user_id)
    return RedirectResponse(url="/admin/users?ok=Deleted", status_code=303)


@router.get("/admin/users/{user_id}/conversations/{conversation_id}")
async def admin_conversation(request: Request, user_id: int, conversation_id: str):
    return RedirectResponse(url="/admin/users", status_code=303)


@router.get("/admin/roster")
async def admin_roster_page(request: Request):
    return _admin_workspace(request, "roster")


@router.post("/admin/roster/import")
async def admin_roster_import(request: Request, file: UploadFile = File(...)):
    admin, deny = _require_admin_page(request)
    if deny:
        return deny
    from app.api.roster import _finish_import

    raw = (await file.read()).decode("utf-8", errors="replace")
    auth = _auth_user(admin)
    with Session(_db_engine(request)) as db:
        result = _finish_import(db, auth, raw)
    return RedirectResponse(
        url=f"/admin/roster?ok=Imported+{result.created}+created,+{result.updated}+updated",
        status_code=303,
    )


@router.post("/admin/roster/{claim_id}/reset-password")
async def admin_roster_reset_pw(request: Request, claim_id: str):
    admin, deny = _require_admin_page(request)
    if deny:
        return deny
    from app.api.roster import admin_reset_group_password

    auth = _auth_user(admin)
    with Session(_db_engine(request)) as db:
        result = admin_reset_group_password(claim_id, request, auth, db)
    return RedirectResponse(
        url=f"/admin/roster?ok=Password+reset&password={result.password}&username={result.username}",
        status_code=303,
    )


@router.post("/admin/roster/{claim_id}/delete")
async def admin_roster_delete(request: Request, claim_id: str):
    admin, deny = _require_admin_page(request)
    if deny:
        return deny
    from app.api.roster import admin_delete_group

    auth = _auth_user(admin)
    with Session(_db_engine(request)) as db:
        admin_delete_group(claim_id, request, auth, db)
    return RedirectResponse(url="/admin/roster?ok=Deleted", status_code=303)


@router.get("/admin/teams")
async def admin_teams_page(request: Request):
    return _admin_workspace(request, "teams")


@router.post("/admin/teams")
async def admin_teams_create(
    request: Request,
    name: str = Form(...),
    scenario_slug: str = Form("library"),
):
    admin, deny = _require_admin_page(request)
    if deny:
        return deny
    from app.api.teams import _unique_invite

    with Session(_db_engine(request)) as db:
        team = Team(
            name=name.strip(),
            scenario_slug=scenario_slug.strip() or "library",
            invite_code=_unique_invite(db),
            participant_names=[],
            roster_member_ids=[],
        )
        db.add(team)
        db.commit()
    return RedirectResponse(url="/admin/teams?ok=Created", status_code=303)


@router.get("/admin/tokens")
async def admin_tokens_page(request: Request):
    return _admin_workspace(request, "tokens")


@router.get("/admin/app-keys")
async def admin_app_keys_page(request: Request):
    return _admin_workspace(request, "appkeys")


@router.post("/admin/app-keys")
async def admin_app_keys_save(request: Request):
    admin, deny = _require_admin_page(request)
    if deny:
        return deny
    from app.security.secret_store import encrypt_secret

    form = await request.form()
    store = _store(request)
    for pid in ("openai", "anthropic", "gemini", "groq", "openrouter"):
        if form.get(f"clear_{pid}"):
            store.set_app_api_config(provider=pid, api_key="", base_url=None)
            continue
        raw = (form.get(pid) or "").strip()
        if not raw:
            continue
        store.set_app_api_config(provider=pid, api_key=encrypt_secret(raw), base_url=None)
    return RedirectResponse(url="/admin/app-keys?ok=Saved", status_code=303)


@router.get("/admin/defaults")
async def admin_defaults_page(request: Request):
    return _admin_workspace(request, "defaults")


@router.post("/admin/defaults")
async def admin_defaults_save(request: Request):
    admin, deny = _require_admin_page(request)
    if deny:
        return deny
    form = await request.form()

    def num(key: str, default: int) -> int:
        try:
            return int(form.get(key) or default)
        except Exception:
            return default

    def text(key: str) -> Optional[str]:
        v = (form.get(key) or "").strip()
        return v or None

    _store(request).update_app_settings(
        default_response_mode=text("tester_default_response_mode"),
        default_llm_choice=text("tester_default_llm_choice"),
        tester_token_limit=num("tester_token_limit", 15000),
        student_default_response_mode=text("student_default_response_mode"),
        student_default_llm_choice=text("student_default_llm_choice"),
        student_token_limit=num("student_token_limit", 15000),
        admin_default_response_mode=text("admin_default_response_mode"),
        admin_default_llm_choice=text("admin_default_llm_choice"),
        admin_token_limit=num("admin_token_limit", 50000),
        apply_budgets=True,
    )
    return RedirectResponse(url="/admin/defaults?ok=Saved", status_code=303)
