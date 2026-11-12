"""Admin API: user management, token monitoring, transcripts, app-wide keys/defaults."""

from __future__ import annotations

from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request, Response
from sqlmodel import Session, select

from app.api.schemas import (
    AdminAppKeysGetResponse,
    AdminAppKeysSetRequest,
    AdminAppSettings,
    AdminAppSettingsUpdate,
    AdminConversationDetail,
    AdminConversationSummary,
    AdminTokenSummary,
    AdminUserCreateRequest,
    AdminUserDeleteRequest,
    AdminUserDeleteResult,
    AdminUserSummary,
    AdminUserUpdateRequest,
    ChatMessage,
    ProviderKeyEntry,
)
from app.security.secret_store import (
    decrypt_secret,
    encrypt_secret,
    is_unchanged_api_key,
    mask_secret,
)
from app.db import get_engine
from app.models.exit import AuditEvent, ClassStudent, GroupClaim, TeamMember
from app.storage.conversation_store import (
    ROLE_ADMIN,
    ROLE_STUDENT,
    ROLE_TESTER,
    VALID_ROLES,
    normalize_role,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])

VALID_RESPONSE_MODES = {
    "vector",
    "neo4j",
    "hybrid",
    "direct",
    "yaml",
    "scenario",
    "compare",
}


def _store(request: Request):
    return request.app.state.conversation_store


def _require_admin(request: Request):
    getter = getattr(request.app.state, "get_current_user", None)
    if not callable(getter):
        raise HTTPException(status_code=500, detail="Auth not configured")
    user = getter(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    role = normalize_role(getattr(user, "role", None), is_admin=bool(getattr(user, "is_admin", False)))
    if role != ROLE_ADMIN and not bool(getattr(user, "is_admin", False)):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def _remaining(user) -> Optional[int]:
    limit = int(getattr(user, "token_limit", 0) or 0)
    used = int(getattr(user, "tokens_used", 0) or 0)
    return max(0, limit - used) if limit > 0 else None


def _user_role(user) -> str:
    return normalize_role(getattr(user, "role", None), is_admin=bool(getattr(user, "is_admin", False)))


def _claimed_group_names() -> Dict[int, str]:
    """Map shared-login user id → roster claim group name."""
    try:
        with Session(get_engine()) as db:
            rows = list(db.exec(select(GroupClaim)).all())
    except Exception:
        return {}
    out: Dict[int, str] = {}
    for claim in rows:
        uid = getattr(claim, "account_user_id", None)
        name = (getattr(claim, "name", None) or "").strip()
        if uid is None or not name:
            continue
        out[int(uid)] = name
    return out


def _user_summary(store, user, settings=None, claimed_groups: Optional[Dict[int, str]] = None) -> AdminUserSummary:
    role = _user_role(user)
    role_defs = store.role_defaults(role, settings)
    user_mode = (getattr(user, "default_response_mode", None) or "").strip() or None
    user_llm = (getattr(user, "default_llm_choice", None) or "").strip() or None
    claimed = None
    if claimed_groups is not None and user.id is not None:
        claimed = claimed_groups.get(int(user.id))
    group_name = claimed or getattr(user, "group_name", None)
    return AdminUserSummary(
        id=user.id,
        username=user.username,
        is_admin=role == ROLE_ADMIN,
        role=role,
        can_select_mode_model=role in (ROLE_ADMIN, ROLE_TESTER),
        group_name=group_name,
        admin_notes=getattr(user, "admin_notes", None),
        token_limit=int(getattr(user, "token_limit", 0) or 0),
        tokens_used=int(getattr(user, "tokens_used", 0) or 0),
        tokens_remaining=_remaining(user),
        budget_is_override=bool(getattr(user, "budget_is_override", False)),
        default_response_mode=user_mode,
        default_llm_choice=user_llm,
        mode_is_override=bool(user_mode),
        llm_is_override=bool(user_llm),
        role_default_response_mode=role_defs.get("default_response_mode"),
        role_default_llm_choice=role_defs.get("default_llm_choice"),
        role_token_limit=int(role_defs.get("token_limit") or 0),
        effective_response_mode=user_mode or role_defs.get("default_response_mode"),
        effective_llm_choice=user_llm or role_defs.get("default_llm_choice"),
        conversation_count=store.count_conversations_for_user(user.id),
        created_at=user.created_at.isoformat() if user.created_at else "",
    )


def _validate_role(role: Optional[str]) -> Optional[str]:
    if role is None:
        return None
    cleaned = (role or "").strip().lower()
    if cleaned not in VALID_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid role '{role}'. Expected one of: {', '.join(sorted(VALID_ROLES))}",
        )
    return cleaned


def _settings_payload(settings) -> AdminAppSettings:
    return AdminAppSettings(
        default_response_mode=settings.default_response_mode or "vector",
        default_llm_choice=settings.default_llm_choice,
        tester_token_limit=int(getattr(settings, "tester_token_limit", None) or 15_000),
        student_default_response_mode=getattr(settings, "student_default_response_mode", None) or "vector",
        student_default_llm_choice=getattr(settings, "student_default_llm_choice", None),
        student_token_limit=int(getattr(settings, "student_token_limit", None) or 15_000),
        admin_default_response_mode=getattr(settings, "admin_default_response_mode", None),
        admin_default_llm_choice=getattr(settings, "admin_default_llm_choice", None),
        admin_token_limit=int(getattr(settings, "admin_token_limit", None) or 50_000),
        updated_at=settings.updated_at.isoformat() if settings.updated_at else None,
    )


def _validate_mode(mode: Optional[str]) -> Optional[str]:
    if mode is None:
        return None
    cleaned = (mode or "").strip().lower()
    if not cleaned:
        return None
    if cleaned not in VALID_RESPONSE_MODES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid response mode '{mode}'. Expected one of: {', '.join(sorted(VALID_RESPONSE_MODES))}",
        )
    return cleaned


@router.get("/users", response_model=List[AdminUserSummary])
async def list_users(request: Request, group: Optional[str] = None):
    _require_admin(request)
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


@router.get("/groups", response_model=List[str])
async def list_groups(request: Request):
    _require_admin(request)
    return _store(request).list_group_names()


@router.post("/users", response_model=AdminUserSummary)
async def create_user(body: AdminUserCreateRequest, request: Request):
    _require_admin(request)
    store = _store(request)
    mode = _validate_mode(body.default_response_mode)
    role = _validate_role(body.role)
    if role is None and body.is_admin:
        role = ROLE_ADMIN
    if role is None:
        role = ROLE_STUDENT
    try:
        user = store.create_user(
            body.username,
            body.password,
            token_limit=body.token_limit,
            budget_is_override=body.budget_is_override,
            role=role,
            is_admin=role == ROLE_ADMIN,
            group_name=body.group_name,
            admin_notes=body.admin_notes,
            default_response_mode=mode,
            default_llm_choice=body.default_llm_choice,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _user_summary(store, user)


@router.get("/users/{user_id}", response_model=AdminUserSummary)
async def get_user(user_id: int, request: Request):
    _require_admin(request)
    store = _store(request)
    user = store.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return _user_summary(store, user, claimed_groups=_claimed_group_names())


@router.patch("/users/{user_id}", response_model=AdminUserSummary)
async def update_user(user_id: int, body: AdminUserUpdateRequest, request: Request):
    admin = _require_admin(request)
    store = _store(request)
    existing = store.get_user_by_id(user_id)
    if not existing:
        raise HTTPException(status_code=404, detail="User not found")

    tokens_used = body.tokens_used
    if body.reset_tokens:
        tokens_used = 0

    mode = None
    clear_mode = bool(body.clear_default_response_mode) or bool(body.reset_mode_to_role)
    if body.default_response_mode is not None and not clear_mode:
        mode = _validate_mode(body.default_response_mode)

    role = _validate_role(body.role)
    # Prevent demoting yourself accidentally with no other admin path
    if existing.id == admin.id:
        if (role is not None and role != ROLE_ADMIN) or body.is_admin is False:
            raise HTTPException(status_code=400, detail="Cannot remove your own admin role")

    updated = store.update_user(
        user_id,
        token_limit=body.token_limit,
        tokens_used=tokens_used,
        role=role,
        is_admin=body.is_admin if role is None else (role == ROLE_ADMIN),
        group_name=body.group_name,
        clear_group=bool(body.clear_group),
        admin_notes=body.admin_notes,
        default_response_mode=mode,
        clear_default_response_mode=clear_mode,
        default_llm_choice=body.default_llm_choice,
        clear_default_llm_choice=bool(body.clear_default_llm_choice) or bool(body.reset_llm_to_role),
        budget_is_override=body.budget_is_override,
        reset_budget_to_role=bool(body.reset_budget_to_role),
        reset_mode_to_role=bool(body.reset_mode_to_role),
        reset_llm_to_role=bool(body.reset_llm_to_role),
        reset_defaults_to_role=bool(body.reset_defaults_to_role),
        password=body.password,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="User not found")
    return _user_summary(store, updated, claimed_groups=_claimed_group_names())


def _cleanup_exit_membership(user_id: int, actor_id: int | None = None) -> None:
    """Release roster claim / team membership owned by this login (best-effort)."""
    try:
        with Session(get_engine()) as db:
            claims = list(
                db.exec(select(GroupClaim).where(GroupClaim.account_user_id == user_id)).all()
            )
            for claim in claims:
                for row in db.exec(
                    select(ClassStudent).where(ClassStudent.group_claim_id == claim.id)
                ).all():
                    row.status = "available"
                    row.group_claim_id = None
                    db.add(row)
                for m in db.exec(select(TeamMember).where(TeamMember.team_id == claim.team_id)).all():
                    db.delete(m)
                db.add(
                    AuditEvent(
                        actor_id=actor_id,
                        action="admin.user.delete_claim",
                        target_id=claim.id,
                        metadata_json=None,
                    )
                )
                db.delete(claim)
            for m in db.exec(select(TeamMember).where(TeamMember.user_id == user_id)).all():
                db.delete(m)
            db.commit()
    except Exception:
        # Exit tables may be unavailable in some test setups; user row still deletes.
        return


def _delete_one_user(store, user_id: int, *, actor_id: int, actor_username: str) -> None:
    target = store.get_user_by_id(user_id)
    if target is None:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")
    if int(user_id) == int(actor_id):
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    if (target.username or "").strip().lower() == (actor_username or "").strip().lower():
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    _cleanup_exit_membership(int(user_id), actor_id=actor_id)
    if not store.delete_user(int(user_id)):
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")


@router.post("/users/bulk-delete", response_model=AdminUserDeleteResult)
async def bulk_delete_users(body: AdminUserDeleteRequest, request: Request):
    admin = _require_admin(request)
    store = _store(request)
    ids = list(dict.fromkeys(int(x) for x in (body.user_ids or []) if x is not None))
    if not ids:
        raise HTTPException(status_code=400, detail="user_ids required")
    deleted: List[int] = []
    skipped: List[int] = []
    failed: List[dict] = []
    for uid in ids:
        if int(uid) == int(admin.id):
            skipped.append(uid)
            continue
        try:
            _delete_one_user(
                store,
                uid,
                actor_id=int(admin.id),
                actor_username=str(getattr(admin, "username", "") or ""),
            )
            deleted.append(uid)
        except HTTPException as exc:
            failed.append({"id": uid, "detail": exc.detail})
        except Exception as exc:
            failed.append({"id": uid, "detail": str(exc)})
    return AdminUserDeleteResult(deleted=deleted, skipped=skipped, failed=failed)


@router.delete("/users/{user_id}", response_model=AdminUserDeleteResult)
async def delete_user(user_id: int, request: Request):
    admin = _require_admin(request)
    store = _store(request)
    _delete_one_user(
        store,
        user_id,
        actor_id=int(admin.id),
        actor_username=str(getattr(admin, "username", "") or ""),
    )
    return AdminUserDeleteResult(deleted=[user_id], skipped=[], failed=[])


@router.get("/tokens", response_model=AdminTokenSummary)
async def token_monitor(request: Request):
    _require_admin(request)
    store = _store(request)
    summary = store.token_usage_summary()
    settings = store.get_app_settings()
    claimed = _claimed_group_names()
    users = [_user_summary(store, u, settings, claimed_groups=claimed) for u in store.list_users()]
    return AdminTokenSummary(
        user_count=summary["user_count"],
        total_token_limit=summary["total_token_limit"],
        total_tokens_used=summary["total_tokens_used"],
        exhausted_users=summary["exhausted_users"],
        by_group=summary["by_group"],
        users=users,
    )


@router.get("/users/{user_id}/conversations", response_model=List[AdminConversationSummary])
async def list_user_conversations(user_id: int, request: Request):
    _require_admin(request)
    store = _store(request)
    user = store.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    convos = store.list_conversations_for_user(user_id)
    counts = store.conversation_message_counts([c.id for c in convos])
    out: List[AdminConversationSummary] = []
    for convo in convos:
        out.append(
            AdminConversationSummary(
                id=convo.id,
                title=convo.title,
                scenario_slug=getattr(convo, "scenario_slug", None),
                message_count=int(counts.get(convo.id, 0)),
                created_at=convo.created_at.isoformat(),
                updated_at=convo.updated_at.isoformat(),
            )
        )
    return out


@router.get("/users/{user_id}/conversations/{conversation_id}", response_model=AdminConversationDetail)
async def get_user_conversation(user_id: int, conversation_id: str, request: Request):
    _require_admin(request)
    store = _store(request)
    user = store.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    convo = store.get_conversation(conversation_id)
    if not convo or convo.user_id != user_id:
        raise HTTPException(status_code=404, detail="Conversation not found")
    messages = store.get_messages(conversation_id)
    return AdminConversationDetail(
        id=convo.id,
        title=convo.title,
        scenario_slug=getattr(convo, "scenario_slug", None),
        user_id=user.id,
        username=user.username,
        created_at=convo.created_at.isoformat(),
        updated_at=convo.updated_at.isoformat(),
        messages=[
            ChatMessage(
                role=m.role,
                content=m.content,
                created_at=m.created_at.isoformat() if getattr(m, "created_at", None) else None,
                mode_used=getattr(m, "mode_used", None),
            )
            for m in messages
        ],
    )


@router.get("/users/{user_id}/conversations/{conversation_id}/download")
async def download_user_conversation(
    user_id: int,
    conversation_id: str,
    request: Request,
    format: str = "txt",
):
    _require_admin(request)
    store = _store(request)
    user = store.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    convo = store.get_conversation(conversation_id)
    if not convo or convo.user_id != user_id:
        raise HTTPException(status_code=404, detail="Conversation not found")
    messages = store.get_messages(conversation_id)
    fmt = (format or "txt").strip().lower()
    safe_title = "".join(c if c.isalnum() or c in "-_" else "_" for c in (convo.title or "transcript"))[:48]
    filename = f"{user.username}_{safe_title}_{conversation_id[:8]}"

    if fmt == "json":
        import json

        payload = {
            "conversation_id": convo.id,
            "title": convo.title,
            "scenario_slug": getattr(convo, "scenario_slug", None),
            "user_id": user.id,
            "username": user.username,
            "created_at": convo.created_at.isoformat(),
            "updated_at": convo.updated_at.isoformat(),
            "messages": [{"role": m.role, "content": m.content, "mode_used": m.mode_used} for m in messages],
        }
        body = json.dumps(payload, indent=2, ensure_ascii=False)
        return Response(
            content=body,
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{filename}.json"'},
        )

    lines = [
        f"Transcript: {convo.title}",
        f"User: {user.username} (id={user.id})",
        f"Scenario: {getattr(convo, 'scenario_slug', None) or '(none)'}",
        f"Created: {convo.created_at.isoformat()}",
        f"Updated: {convo.updated_at.isoformat()}",
        "",
    ]
    for m in messages:
        role = (m.role or "unknown").upper()
        if fmt == "md":
            lines.append(f"### {role}")
            lines.append("")
            lines.append(m.content or "")
            lines.append("")
        else:
            lines.append(f"[{role}]")
            lines.append(m.content or "")
            lines.append("")
    text = "\n".join(lines)
    ext = "md" if fmt == "md" else "txt"
    media = "text/markdown" if fmt == "md" else "text/plain"
    return Response(
        content=text,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}.{ext}"'},
    )


@router.get("/settings", response_model=AdminAppSettings)
async def get_settings(request: Request):
    _require_admin(request)
    return _settings_payload(_store(request).get_app_settings())


@router.patch("/settings", response_model=AdminAppSettings)
async def update_settings(body: AdminAppSettingsUpdate, request: Request):
    _require_admin(request)
    mode = _validate_mode(body.default_response_mode) if body.default_response_mode is not None else None
    student_mode = (
        _validate_mode(body.student_default_response_mode)
        if body.student_default_response_mode is not None
        else None
    )
    admin_mode = None
    if body.admin_default_response_mode is not None and not body.clear_admin_default_response_mode:
        admin_mode = _validate_mode(body.admin_default_response_mode)
    settings = _store(request).update_app_settings(
        default_response_mode=mode,
        default_llm_choice=body.default_llm_choice,
        clear_default_llm_choice=bool(body.clear_default_llm_choice),
        tester_token_limit=body.tester_token_limit,
        student_default_response_mode=student_mode,
        student_default_llm_choice=body.student_default_llm_choice,
        clear_student_default_llm_choice=bool(body.clear_student_default_llm_choice),
        student_token_limit=body.student_token_limit,
        admin_default_response_mode=admin_mode,
        clear_admin_default_response_mode=bool(body.clear_admin_default_response_mode),
        admin_default_llm_choice=body.admin_default_llm_choice,
        clear_admin_default_llm_choice=bool(body.clear_admin_default_llm_choice),
        admin_token_limit=body.admin_token_limit,
        apply_budgets=body.apply_budgets is not False,
    )
    return _settings_payload(settings)


@router.get("/app-keys", response_model=AdminAppKeysGetResponse)
async def get_app_keys(request: Request):
    _require_admin(request)
    entries: List[ProviderKeyEntry] = []
    for cfg in _store(request).get_all_app_api_configs():
        plain = decrypt_secret(cfg.api_key) if cfg.api_key else ""
        masked = mask_secret(plain) if plain else None
        entries.append(
            ProviderKeyEntry(
                provider=cfg.provider,
                api_key_hint=masked,
                api_key_masked=masked,
                has_key=bool(plain),
                base_url=cfg.base_url,
                scope="app",
            )
        )
    return AdminAppKeysGetResponse(keys=entries)


@router.post("/app-keys")
async def set_app_keys(body: AdminAppKeysSetRequest, request: Request):
    _require_admin(request)
    store = _store(request)
    for entry in body.keys:
        provider = (entry.provider or "").strip().lower()
        if not provider:
            continue
        existing = store.get_app_api_config(provider)
        if is_unchanged_api_key(entry.api_key):
            stored_key = existing.api_key if existing else ""
        elif not (entry.api_key or "").strip():
            stored_key = ""
        else:
            stored_key = encrypt_secret(entry.api_key.strip())
        store.set_app_api_config(
            provider=provider,
            api_key=stored_key,
            base_url=entry.base_url,
        )
    return {"status": "ok"}


@router.post("/scenarios/reindex")
async def reindex_scenarios(request: Request):
    """Reload YAML scenario packages and refresh vector + graph indexes (and in-memory yaml/direct packs)."""
    _require_admin(request)
    from app.indexing import reload_and_index_scenarios

    store = _store(request)
    rag_systems = getattr(request.app.state, "rag_systems", None) or {}
    result = reload_and_index_scenarios(
        engine=store.engine,
        vector_rag=rag_systems.get("vector"),
        neo4j_rag=rag_systems.get("neo4j"),
    )
    return {"status": "ok", **result}
