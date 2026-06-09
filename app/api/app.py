"""
FastAPI backend for Requirements Chatbot.
"""

# Apply pytree compatibility fix
try:
    import app.fix_pytree  # noqa: F401
except ImportError:
    pass

import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

# Package dir (`app/`) and repo root — load `.env` from `app/` first, then project root, then cwd.
APP_DIR = Path(__file__).resolve().parents[1]
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
try:
    from dotenv import load_dotenv

    _app_env = APP_DIR / ".env"
    _root_env = _PROJECT_ROOT / ".env"
    load_dotenv(dotenv_path=_app_env)
    load_dotenv(dotenv_path=_root_env)
    load_dotenv()
    if _app_env.is_file():
        print(f"[ok] Loaded environment variables from {_app_env}")
    elif _root_env.is_file():
        print(f"[ok] Loaded environment variables from {_root_env}")
    else:
        print(f"[warn] No {_app_env} or {_root_env} — using OS env and cwd .env if any")
except ImportError:
    print("[warn] python-dotenv not installed. Install with: pip install python-dotenv")
    print("  Continuing without .env file support...")
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import jinja2
from fastapi.templating import Jinja2Templates

from app.api.schemas import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    ConversationDetail,
    ConversationSummary,
    FeedbackRequest,
    LoginRequest,
    LoginResponse,
    ProviderKeyEntry,
    ReflectionAnalyzeRequest,
    ReflectionApplyRequest,
    ReflectionThreadChatRequest,
    ReflectionThreadDetail,
    ReflectionThreadStartResponse,
    ReflectionThreadSummary,
    UserConfigGetResponse,
    UserConfigProviderSet,
    UserConfigSetRequest,
)
from app.storage.conversation_store import ConversationStore, User
from app.tweaks.behavior_tweaks import BehaviorTweaksStore
from app.llm_wrapper import LLMWrapper
from app.llm_registry import (
    choice_label,
    default_choice_id,
    list_llm_choices,
    openai_configured,
    ollama_reachable,
    parse_choice_id,
    resolve_llm_wrapper,
    validate_choice_id,
    anthropic_configured,
)
from app.rag_backend import RequirementsRAG
from app.rag_backend_neo4j import RequirementsRAGNeo4j
from app.mcp.hybrid import HybridKnowledgeService
from app.reflection import (
    REFLECTION_CHAT_SYSTEM,
    REFLECTION_SYSTEM,
    build_reflection_chat_payload,
    build_reflection_user_payload,
    compact_transcript,
    compact_tweak_snapshot,
    normalize_reflection_payload,
    parse_reflection_json,
    pick_reflection_llm,
    split_reflection_response_fallback,
)

hybrid_service: Optional[HybridKnowledgeService] = None

# ── Auth helpers ──────────────────────────────────────────────

def _get_token_from_header(request: Request) -> Optional[str]:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None

def _get_current_user(request: Request) -> Optional[User]:
    token = _get_token_from_header(request)
    if not token:
        return None
    session = conversation_store.get_session(token)
    if not session:
        return None
    return conversation_store.get_user_by_id(session.user_id)


@asynccontextmanager
async def _app_lifespan(_app: FastAPI):
    global hybrid_service
    hybrid_service = HybridKnowledgeService(
        rag_systems.get("vector"),
        rag_systems.get("neo4j"),
        hybrid_top_k=hybrid_top_k,
        hybrid_route_margin=hybrid_route_margin,
    )
    conversation_store.seed_users()
    yield


app = FastAPI(title="Requirements Chatbot API", lifespan=_app_lifespan)
WEB_DIR = APP_DIR / "web"
TEMPLATES_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"
templates = Jinja2Templates(
    directory=str(TEMPLATES_DIR),
    autoescape=jinja2.select_autoescape(["html", "xml"]),
    cache_size=0,
)
conversation_store = ConversationStore(
    os.getenv("CONVERSATION_DB_URL")
    or os.getenv("DATABASE_URL")
    or "sqlite:///./storage/conversations.db"
)
conversation_store.init()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

excel_file = os.getenv("EXCEL_FILE", "data.xlsx")
print(f"Using Excel file: {excel_file}")
chroma_persist_directory = os.getenv("CHROMA_PERSIST_DIRECTORY", "./storage/chroma_db_v2")
neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
neo4j_user = os.getenv("NEO4J_USER", "neo4j")
neo4j_password = os.getenv("NEO4J_PASSWORD", "password")

print("Initializing RAG systems for comparison...")
rag_systems: Dict[str, Optional[object]] = {"vector": None, "neo4j": None}
engine_status: Dict[str, str] = {"vector": "not_initialized", "neo4j": "not_initialized"}

try:
    rag_systems["vector"] = RequirementsRAG(excel_file, persist_directory=chroma_persist_directory)
    engine_status["vector"] = "ready"
    print("✓ Vector RAG (ChromaDB) initialized")
except Exception as e:
    engine_status["vector"] = f"error: {e}"
    print(f"⚠ Vector RAG initialization failed: {e}")

try:
    rag_systems["neo4j"] = RequirementsRAGNeo4j(
        excel_file,
        neo4j_uri=neo4j_uri,
        neo4j_user=neo4j_user,
        neo4j_password=neo4j_password,
    )
    engine_status["neo4j"] = "ready"
    print("✓ Neo4j structured RAG initialized")
except ImportError:
    engine_status["neo4j"] = "error: neo4j package not installed"
except Exception as e:
    engine_status["neo4j"] = f"error: {e}"

llm_backend = os.getenv("LLM_BACKEND", "ollama").lower()
llm_model = os.getenv("LLM_MODEL", None)
print(f"Initializing LLM backend: {llm_backend}...")
llm_by_mode: Dict[str, Optional[LLMWrapper]] = {
    "vector": LLMWrapper(rag_systems["vector"], backend=llm_backend, model=llm_model)
    if rag_systems["vector"]
    else None,
    "neo4j": LLMWrapper(rag_systems["neo4j"], backend=llm_backend, model=llm_model)
    if rag_systems["neo4j"]
    else None,
}

hybrid_top_k = int(os.getenv("HYBRID_TOP_K", "3"))
hybrid_route_margin = float(os.getenv("HYBRID_ROUTE_MARGIN", "0.15"))
_tweak_raw = os.getenv("TWEAK_MODE_ENABLED", "")
tweak_mode_enabled = _tweak_raw.strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
    "enabled",
)
behavior_tweaks_file = os.getenv("BEHAVIOR_TWEAKS_FILE", "config/behavior/behavior_tweaks.json")
behavior_tweaks = BehaviorTweaksStore(behavior_tweaks_file) if tweak_mode_enabled else None
print("RAG system ready!")


def _behavior_system_suffix() -> str:
    """Stakeholder prompt additions from behavior_tweaks (generation-time; post-process rules stay separate)."""
    if not tweak_mode_enabled or behavior_tweaks is None:
        return ""
    return behavior_tweaks.system_suffix_for_llm()


def _user_api_overrides(user: Optional[User]) -> dict:
    """Return provider/api_key/base_url from user's config, or empty dict."""
    if not user:
        return {}
    all_cfgs = conversation_store.get_all_user_api_configs(user.id)
    providers = {}
    for cfg in all_cfgs:
        if cfg.api_key and cfg.provider:
            providers[cfg.provider.lower()] = {
                "api_key": cfg.api_key,
                "base_url": cfg.base_url,
            }
    return {"user_providers": providers}


def _get_user_provider_override(user: Optional[User], backend: str) -> dict:
    """Get the override for a specific backend from user's stored configs."""
    overrides = _user_api_overrides(user)
    providers = overrides.get("user_providers", {})
    info = providers.get(backend.lower())
    if info and info.get("api_key"):
        return {
            "provider_override": backend,
            "api_key_override": info["api_key"],
            "base_url_override": info.get("base_url"),
        }
    return {}


def _rag_for_mode(mode: str):
    if mode == "neo4j":
        return rag_systems.get("neo4j")
    return rag_systems.get("vector")


def _llm_used_payload(choice_id: str, user_provider: str = "") -> Dict[str, str]:
    backend, model = parse_choice_id(choice_id)
    return {
        "id": choice_id,
        "backend": backend or "",
        "model": model or "",
        "label": choice_label(choice_id, user_provider=user_provider),
    }


def _generate_mode_response(
    mode: str,
    message: str,
    history: List[Dict],
    *,
    user: Optional[User] = None,
    force_coach: bool = False,
    llm_choice: Optional[str] = None,
) -> tuple[str, str, str]:
    """Returns (response_text, mode_used label, resolved llm_choice id)."""
    rag = _rag_for_mode(mode)
    if not rag:
        status = engine_status.get(mode, "unavailable")
        raise ValueError(f"Mode '{mode}' is unavailable ({status})")
    resolved_choice = validate_choice_id(llm_choice, user_provider="")
    backend, _ = parse_choice_id(resolved_choice)
    user_override = _get_user_provider_override(user, backend or "")
    user_provider = (backend or "") if user_override else ""
    resolved_choice = validate_choice_id(llm_choice, user_provider=user_provider)
    llm = resolve_llm_wrapper(rag, resolved_choice)
    response, style = llm.generate_response(
        message,
        conversation_history=history,
        behavior_system_suffix=_behavior_system_suffix(),
        force_coach=force_coach,
        **user_override,
    )
    if force_coach or style == "coach":
        return response, "coach", resolved_choice
    return response, mode, resolved_choice


def _finalize_response(query: str, response: str, mode_label: str) -> str:
    if mode_label == "coach" or mode_label.endswith(":coach"):
        return response
    return _apply_runtime_tweaks(query, response)


def _apply_runtime_tweaks(query: str, response: str) -> str:
    if not tweak_mode_enabled or behavior_tweaks is None:
        return response
    return behavior_tweaks.apply_to_response(query, response)


# ── Auth endpoints ────────────────────────────────────────────

@app.post("/api/auth/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    user = conversation_store.get_user_by_credentials(request.username, request.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = conversation_store.create_session(user.id)
    return LoginResponse(token=token, user_id=user.id, username=user.username)

@app.post("/api/auth/logout")
async def logout(request: Request):
    token = _get_token_from_header(request)
    if token:
        conversation_store.delete_session(token)
    return {"status": "ok"}

@app.get("/api/auth/me")
async def me(request: Request):
    user = _get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {"user_id": user.id, "username": user.username}

# ── User API config ───────────────────────────────────────────

@app.get("/api/user/config", response_model=UserConfigGetResponse)
async def get_user_config(request: Request):
    user = _get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    all_cfgs = conversation_store.get_all_user_api_configs(user.id)
    entries = []
    for cfg in all_cfgs:
        hint = None
        if cfg.api_key:
            key = cfg.api_key
            hint = f"{key[:5]}...{key[-3:]}" if len(key) > 10 else "***"
        entries.append(
            ProviderKeyEntry(
                provider=cfg.provider,
                api_key_hint=hint,
                has_key=bool(cfg.api_key),
                base_url=cfg.base_url,
            )
        )
    return UserConfigGetResponse(keys=entries)

@app.post("/api/user/config")
async def set_user_config(request: Request, body: UserConfigSetRequest):
    user = _get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    for entry in body.keys:
        conversation_store.set_user_api_config(
            user.id,
            provider=entry.provider,
            api_key=entry.api_key,
            base_url=entry.base_url,
        )
    return {"status": "ok"}

# ── App endpoints ─────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    user = _get_current_user(request)
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "authenticated": user is not None,
            "username": user.username if user else None,
        },
    )


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, req: Request):
    user = _get_current_user(req)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        conversation_id = request.conversation_id
        if conversation_id:
            convo = conversation_store.get_conversation(conversation_id)
            if not convo:
                raise ValueError(f"Conversation '{conversation_id}' not found")
            if convo.user_id != user.id:
                raise HTTPException(status_code=403, detail="Not your conversation")
        else:
            convo = conversation_store.create_conversation(first_prompt=request.message, user_id=user.id if user else 0)
            conversation_id = convo.id

        conversation_store.add_message(conversation_id=conversation_id, role="user", content=request.message, mode_used=None)
        stored_messages = conversation_store.get_messages(conversation_id)
        history = [{"role": m.role, "content": m.content} for m in stored_messages[:-1]]
        mode = (request.response_mode or "vector").lower()
        user_overrides = _user_api_overrides(user)
        user_providers = user_overrides.get("user_providers", {})
        llm_choice = validate_choice_id(request.llm_choice, user_provider="")

        if mode == "compare":
            vector_response, _, choice_v = _generate_mode_response(
                "vector",
                request.message,
                history,
                user=user,
                llm_choice=llm_choice,
            )
            neo4j_response, _, choice_n = _generate_mode_response(
                "neo4j",
                request.message,
                history,
                user=user,
                llm_choice=llm_choice,
            )
            vector_response = _finalize_response(request.message, vector_response, "vector")
            neo4j_response = _finalize_response(request.message, neo4j_response, "neo4j")
            combined = (
                "<strong>Vector RAG (Embeddings + ChromaDB)</strong><br>"
                f"{vector_response}<br><br>"
                "<strong>Neo4j Structured RAG</strong><br>"
                f"{neo4j_response}"
            )
            conversation_store.add_message(conversation_id=conversation_id, role="assistant", content=combined, mode_used="compare")
            return ChatResponse(
                response=combined,
                sources=None,
                mode_used="compare",
                conversation_id=conversation_id,
                llm_used=_llm_used_payload(choice_v or choice_n or llm_choice),
            )

        if mode == "hybrid":
            if not hybrid_service:
                raise ValueError("Hybrid service is not initialized")
            if not rag_systems["vector"] and not rag_systems["neo4j"]:
                raise ValueError("Hybrid mode requires at least one of vector or neo4j engines")
            rag = rag_systems["vector"] or rag_systems["neo4j"]
            llm = resolve_llm_wrapper(rag, llm_choice)
            resolved_backend, _ = parse_choice_id(llm_choice)
            user_override = _get_user_provider_override(user, resolved_backend or "")
            handoff = hybrid_service.retrieve(request.message, top_k=hybrid_top_k)
            response, style = llm.generate_response_from_results(
                request.message,
                handoff.results,
                conversation_history=history,
                behavior_system_suffix=_behavior_system_suffix(),
                **user_override,
            )
            if style == "coach":
                mode_label = "coach"
            else:
                mode_label = f"hybrid:{handoff.route}"
            response = _finalize_response(request.message, response, mode_label)
            routing_payload = {
                **handoff.routing,
                "backends_used": handoff.backends_used,
            }
            conversation_store.add_message(
                conversation_id=conversation_id,
                role="assistant",
                content=response,
                mode_used=mode_label,
            )
            return ChatResponse(
                response=response,
                sources=None,
                mode_used=mode_label,
                conversation_id=conversation_id,
                routing=routing_payload,
                llm_used=_llm_used_payload(llm_choice),
            )

        if mode == "coach":
            if not rag_systems.get("vector"):
                raise ValueError("Coach mode requires vector RAG (ChromaDB)")
            response, mode_label, resolved = _generate_mode_response(
                "vector",
                request.message,
                history,
                user=user,
                force_coach=True,
                llm_choice=llm_choice,
            )
            response = _finalize_response(request.message, response, mode_label)
            conversation_store.add_message(
                conversation_id=conversation_id,
                role="assistant",
                content=response,
                mode_used=mode_label,
            )
            return ChatResponse(
                response=response,
                sources=None,
                mode_used=mode_label,
                conversation_id=conversation_id,
                llm_used=_llm_used_payload(resolved),
            )

        if mode not in ("vector", "neo4j"):
            raise ValueError("Invalid response_mode. Use: vector, neo4j, hybrid, compare, or coach")

        response, mode_label, resolved = _generate_mode_response(
            mode,
            request.message,
            history,
            user=user,
            llm_choice=llm_choice,
        )
        response = _finalize_response(request.message, response, mode_label)
        conversation_store.add_message(
            conversation_id=conversation_id,
            role="assistant",
            content=response,
            mode_used=mode_label,
        )
        return ChatResponse(
            response=response,
            sources=None,
            mode_used=mode_label,
            conversation_id=conversation_id,
            llm_used=_llm_used_payload(resolved),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/health")
async def health():
    try:
        doc_counts = {}
        doc_counts["vector"] = rag_systems["vector"].collection.count() if rag_systems["vector"] and hasattr(rag_systems["vector"], "collection") else 0
        doc_counts["neo4j"] = rag_systems["neo4j"]._count_nodes() if rag_systems["neo4j"] and hasattr(rag_systems["neo4j"], "_count_nodes") else 0
        return {
            "status": "healthy",
            "engines": engine_status,
            "documents": doc_counts,

        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.get("/api/modes")
async def modes():
    return {
        "available_modes": {
            "vector": llm_by_mode["vector"] is not None,
            "neo4j": llm_by_mode["neo4j"] is not None,
            "hybrid": (
                (rag_systems["vector"] is not None or rag_systems["neo4j"] is not None)
                and (llm_by_mode["vector"] is not None or llm_by_mode["neo4j"] is not None)
            ),
            "compare": (llm_by_mode["vector"] is not None and llm_by_mode["neo4j"] is not None),
            "coach": llm_by_mode["vector"] is not None,
        },
        "engine_status": engine_status,
        "hybrid_routing": "neo4j | chroma | blend per query",
        "coach_hint": "define / explain / what is … questions auto-use domain coach in any mode",
    }


@app.get("/api/conversations", response_model=List[ConversationSummary])
async def list_conversations(request: Request):
    user = _get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    records = conversation_store.list_conversations(user_id=user.id, limit=100)
    return [
        ConversationSummary(
            id=record.id,
            title=record.title,
            created_at=record.created_at.isoformat(),
            updated_at=record.updated_at.isoformat(),
        )
        for record in records
    ]


@app.delete("/api/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str, request: Request):
    user = _get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    convo = conversation_store.get_conversation(conversation_id)
    if not convo:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if convo.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your conversation")
    deleted = conversation_store.delete_conversation(conversation_id)
    return {"status": "ok", "conversation_id": conversation_id}


@app.get("/api/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(conversation_id: str, request: Request):
    user = _get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    convo = conversation_store.get_conversation(conversation_id)
    if not convo:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if convo.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your conversation")
    messages = conversation_store.get_messages(conversation_id)
    return ConversationDetail(
        id=convo.id,
        title=convo.title,
        created_at=convo.created_at.isoformat(),
        updated_at=convo.updated_at.isoformat(),
        messages=[ChatMessage(role=m.role, content=m.content) for m in messages],
    )


@app.get("/api/config")
async def config(request: Request = None):
    active_wrappers = {mode: wrapper for mode, wrapper in llm_by_mode.items() if wrapper is not None}
    llm_runtime = {
        mode: {
            "backend": wrapper.backend,
            "model": wrapper.model,
            "temperature": wrapper.temperature,
            "max_tokens": wrapper.max_tokens,
            "rag_top_k": wrapper.rag_top_k,
        }
        for mode, wrapper in active_wrappers.items()
    }
    user = _get_current_user(request) if request else None
    user_overrides = _user_api_overrides(user) if user else {}
    user_providers = user_overrides.get("user_providers", {})
    user_provider_names = set(user_providers.keys())

    has_openai = "openai" in user_provider_names
    has_anthropic = "anthropic" in user_provider_names
    has_groq = "groq" in user_provider_names
    has_openrouter = "openrouter" in user_provider_names

    # Determine primary user_provider for list_llm_choices
    for p in ("openai", "anthropic"):
        if p in user_provider_names:
            user_llm_provider = p
            break
    else:
        user_llm_provider = ""

    choices = list_llm_choices(user_provider=user_llm_provider)

    switcher_on = (
        has_openai
        or has_anthropic
        or ollama_reachable()
        or len([c for c in choices if c["provider"] != "template"]) > 0
    )
    return {
        "excel_file": excel_file,
        "neo4j_uri": neo4j_uri,
        "engines": engine_status,
        "llm_backend_env": llm_backend,
        "llm_model_env": llm_model,
        "llm_default_choice": default_choice_id(),
        "llm_choices": choices,
        "llm_model_switcher_enabled": switcher_on and len(choices) > 1,
        "llm_providers": {
            "openai": has_openai,
            "anthropic": has_anthropic,
            "groq": has_groq,
            "openrouter": has_openrouter,
            "ollama": ollama_reachable(),
        },
        "hybrid_top_k": hybrid_top_k,
        "hybrid_route_margin": hybrid_route_margin,
        "tweak_mode_enabled": tweak_mode_enabled,
        "tweak_mode_env_set": bool(_tweak_raw.strip()),
        "env_app_dir": str(APP_DIR),
        "env_file_app": str(APP_DIR / ".env"),
        "env_file_app_exists": (APP_DIR / ".env").is_file(),
        "env_file_project_root": str(_PROJECT_ROOT / ".env"),
        "env_file_project_root_exists": (_PROJECT_ROOT / ".env").is_file(),
        "behavior_tweaks_file": behavior_tweaks_file,
        "behavior_tweaks_last_updated": (behavior_tweaks.load().get("last_updated") if behavior_tweaks else None),
        "behavior_system_suffix_chars": (
            len(behavior_tweaks.system_suffix_for_llm()) if behavior_tweaks else 0
        ),
        "conversation_db_url": (
            os.getenv("CONVERSATION_DB_URL")
            or os.getenv("DATABASE_URL")
            or "sqlite:///./storage/conversations.db"
        ),
        "chroma_persist_directory": chroma_persist_directory,
        "llm_runtime_by_mode": llm_runtime,
    }


def _reflection_messages(req: ReflectionAnalyzeRequest) -> List[Dict]:
    if req.messages is not None and len(req.messages) > 0:
        return [{"role": m.role, "content": m.content} for m in req.messages]
    if req.conversation_id:
        convo = conversation_store.get_conversation(req.conversation_id)
        if not convo:
            raise HTTPException(status_code=404, detail="Conversation not found")
        stored = conversation_store.get_messages(req.conversation_id)
        return [{"role": m.role, "content": m.content} for m in stored]
    raise HTTPException(status_code=400, detail="Provide non-empty messages or a conversation_id")


def _thread_to_detail(thread_id: str) -> ReflectionThreadDetail:
    thread = conversation_store.get_reflection_thread(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Reflection thread not found")
    messages = conversation_store.get_reflection_messages(thread_id)
    return ReflectionThreadDetail(
        id=thread.id,
        conversation_id=thread.conversation_id,
        title=thread.title,
        latest_draft_json=thread.latest_draft_json,
        created_at=thread.created_at.isoformat(),
        updated_at=thread.updated_at.isoformat(),
        messages=[ChatMessage(role=m.role, content=m.content) for m in messages],
    )


def _split_reflection_reply(
    raw: str,
    draft_fallback: Optional[Dict[str, Any]] = None,
) -> Dict[str, Dict]:
    notes, parsed = split_reflection_response_fallback(raw, draft_fallback)
    if not notes:
        notes = parsed.get("performance_notes", "") or ""
    return {"notes": notes, "reflection": parsed}


@app.post("/api/reflection/analyze")
async def reflection_analyze(request: ReflectionAnalyzeRequest, req: Request):
    if not _get_current_user(req):
        raise HTTPException(status_code=401, detail="Not authenticated")
    if not tweak_mode_enabled or behavior_tweaks is None:
        raise HTTPException(
            status_code=403,
            detail="Tweak mode is disabled. Set TWEAK_MODE_ENABLED=true to enable reflection.",
        )
    msgs = _reflection_messages(request)
    if len(msgs) < 2:
        raise HTTPException(status_code=400, detail="Need at least two messages to run reflection")

    transcript = compact_transcript(msgs)
    snap = compact_tweak_snapshot(behavior_tweaks.load())
    user_block = build_reflection_user_payload(transcript, snap)
    try:
        mode_name, llm = pick_reflection_llm(llm_by_mode)
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e

    try:
        raw = llm.generate_raw(REFLECTION_SYSTEM, user_block)
        parsed = parse_reflection_json(raw)
    except ValueError as e:
        raise HTTPException(status_code=502, detail=f"Reflection parse error: {e}") from e
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Reflection LLM error: {e}") from e

    return {
        "mode_used": mode_name,
        "reflection": parsed,
        "raw_excerpt": (raw[:1500] + ("…" if len(raw) > 1500 else "")) if raw else "",
    }


@app.get("/api/conversations/{conversation_id}/reflections", response_model=List[ReflectionThreadSummary])
async def list_reflection_threads(conversation_id: str, request: Request):
    if not _get_current_user(request):
        raise HTTPException(status_code=401, detail="Not authenticated")
    convo = conversation_store.get_conversation(conversation_id)
    if not convo:
        raise HTTPException(status_code=404, detail="Conversation not found")
    threads = conversation_store.list_reflection_threads(conversation_id, limit=100)
    return [
        ReflectionThreadSummary(
            id=t.id,
            conversation_id=t.conversation_id,
            title=t.title,
            created_at=t.created_at.isoformat(),
            updated_at=t.updated_at.isoformat(),
        )
        for t in threads
    ]


@app.post("/api/conversations/{conversation_id}/reflections/start", response_model=ReflectionThreadStartResponse)
async def start_reflection_thread(conversation_id: str, request: Request):
    if not _get_current_user(request):
        raise HTTPException(status_code=401, detail="Not authenticated")
    if not tweak_mode_enabled or behavior_tweaks is None:
        raise HTTPException(status_code=403, detail="Tweak mode is disabled.")
    convo = conversation_store.get_conversation(conversation_id)
    if not convo:
        raise HTTPException(status_code=404, detail="Conversation not found")

    base_messages = conversation_store.get_messages(conversation_id)
    msgs = [{"role": m.role, "content": m.content} for m in base_messages]
    if len(msgs) < 2:
        raise HTTPException(status_code=400, detail="Need at least two base conversation messages")

    transcript = compact_transcript(msgs)
    snap = compact_tweak_snapshot(behavior_tweaks.load())
    user_block = build_reflection_user_payload(transcript, snap)
    mode_name, llm = pick_reflection_llm(llm_by_mode)
    raw = llm.generate_raw(REFLECTION_SYSTEM, user_block)
    result = _split_reflection_reply(raw, draft_fallback={})
    reflection = result["reflection"]

    draft_json = json.dumps(reflection, ensure_ascii=False, separators=(",", ":"))
    thread = conversation_store.create_reflection_thread(
        conversation_id=conversation_id,
        title=f"Reflection: {convo.title[:48]}",
        latest_draft_json=draft_json,
    )
    conversation_store.add_reflection_message(
        thread.id,
        "assistant",
        result["notes"] or "Initial reflection draft prepared.",
    )
    detail = _thread_to_detail(thread.id)
    return ReflectionThreadStartResponse(thread=detail, reflection=reflection, mode_used=mode_name)


@app.get("/api/reflections/{thread_id}", response_model=ReflectionThreadDetail)
async def get_reflection_thread(thread_id: str, request: Request):
    if not _get_current_user(request):
        raise HTTPException(status_code=401, detail="Not authenticated")
    return _thread_to_detail(thread_id)


@app.post("/api/reflections/{thread_id}/chat")
async def chat_reflection_thread(thread_id: str, request: ReflectionThreadChatRequest, req: Request):
    if not tweak_mode_enabled or behavior_tweaks is None:
        raise HTTPException(status_code=403, detail="Tweak mode is disabled.")
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Message is required")
    thread = conversation_store.get_reflection_thread(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Reflection thread not found")
    convo_messages = conversation_store.get_messages(thread.conversation_id)
    transcript = compact_transcript([{"role": m.role, "content": m.content} for m in convo_messages])
    snap = compact_tweak_snapshot(behavior_tweaks.load())
    thread_messages = conversation_store.get_reflection_messages(thread_id)
    history = [{"role": m.role, "content": m.content} for m in thread_messages]
    current_draft = request.reflection
    if current_draft is None and thread.latest_draft_json:
        try:
            current_draft = json.loads(thread.latest_draft_json)
        except Exception:
            current_draft = {}
    payload = build_reflection_chat_payload(
        transcript_block=transcript,
        tweak_snapshot_json=snap,
        thread_messages=history,
        user_message=request.message,
        current_draft=current_draft or {},
    )
    mode_name, llm = pick_reflection_llm(llm_by_mode)
    raw = llm.generate_raw(REFLECTION_CHAT_SYSTEM, payload)
    result = _split_reflection_reply(raw, draft_fallback=current_draft or {})
    reflection = result["reflection"]
    draft_json = json.dumps(reflection, ensure_ascii=False, separators=(",", ":"))
    conversation_store.add_reflection_message(thread_id, "user", request.message.strip())
    conversation_store.add_reflection_message(thread_id, "assistant", result["notes"] or "Updated reflection draft.")
    conversation_store.update_reflection_thread_draft(thread_id, draft_json)
    return {"mode_used": mode_name, "reflection": reflection, "assistant_message": result["notes"], "thread": _thread_to_detail(thread_id)}


@app.post("/api/reflections/{thread_id}/apply")
async def apply_reflection_thread(thread_id: str, request: ReflectionApplyRequest, req: Request):
    if not _get_current_user(req):
        raise HTTPException(status_code=401, detail="Not authenticated")
    if not tweak_mode_enabled or behavior_tweaks is None:
        raise HTTPException(status_code=403, detail="Tweak mode is disabled.")
    thread = conversation_store.get_reflection_thread(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Reflection thread not found")
    normalized = normalize_reflection_payload(dict(request.reflection))
    result = behavior_tweaks.apply_reflection_patch(normalized)
    draft_json = json.dumps(normalized, ensure_ascii=False, separators=(",", ":"))
    conversation_store.update_reflection_thread_draft(thread_id, draft_json)
    conversation_store.add_reflection_message(
        thread_id,
        "assistant",
        "Applied current draft to tweaks file.",
    )
    return {
        "status": "ok",
        "message": "Tweak file updated.",
        "changes": result.get("changes", []),
        "last_updated": result.get("last_updated"),
        "thread": _thread_to_detail(thread_id),
    }


@app.post("/api/reflection/apply")
async def reflection_apply(request: ReflectionApplyRequest, req: Request):
    if not _get_current_user(req):
        raise HTTPException(status_code=401, detail="Not authenticated")
    if not tweak_mode_enabled or behavior_tweaks is None:
        raise HTTPException(
            status_code=403,
            detail="Tweak mode is disabled. Set TWEAK_MODE_ENABLED=true to apply reflection patches.",
        )
    normalized = normalize_reflection_payload(dict(request.reflection))
    if not isinstance(normalized.get("patch"), dict):
        raise HTTPException(status_code=400, detail="Invalid reflection payload: missing patch")

    result = behavior_tweaks.apply_reflection_patch(normalized)
    return {
        "status": "ok",
        "message": "Tweak file updated.",
        "changes": result.get("changes", []),
        "last_updated": result.get("last_updated"),
    }


@app.post("/api/feedback")
async def feedback(request: FeedbackRequest, req: Request):
    if not _get_current_user(req):
        raise HTTPException(status_code=401, detail="Not authenticated")
    if not tweak_mode_enabled or behavior_tweaks is None:
        raise HTTPException(status_code=403, detail="Tweak mode is disabled. Set TWEAK_MODE_ENABLED=true to enable feedback loop.")
    result = behavior_tweaks.update_from_feedback(
        query=request.prompt,
        response=request.response,
        feedback=request.feedback,
        desired_response=request.desired_response,
        mode=request.mode_used,
    )
    return {
        "status": "ok",
        "message": "Feedback saved and tweaks updated.",
        "changes": result.get("changes", []),
        "last_updated": result.get("last_updated"),
    }


if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

