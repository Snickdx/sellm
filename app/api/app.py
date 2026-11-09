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
import time
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
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api.schemas import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    ConversationDetail,
    ConversationSummary,
    CreateConversationRequest,
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
from app.api.admin import router as admin_router
from app.storage.conversation_store import (
    ROLE_ADMIN,
    ROLE_STUDENT,
    ROLE_TESTER,
    ConversationStore,
    User,
    normalize_role,
)
from app.tweaks.behavior_tweaks import BehaviorTweaksStore
from app.llm_wrapper import LLMWrapper
from app.seproject.seed import seed_scenarios
from app.seproject.scenarios.registry import scenario_registry
from app.seproject.chat.persona_service import generate_validated_reply, get_persona
from app.seproject.api.scenarios import router as scenarios_router
from app.seproject.api.teams import router as teams_router
from app.seproject.api.repositories import router as repositories_router
from app.seproject.api.exit_interviews import router as exit_interviews_router
from app.seproject.api.voice import router as voice_router
from app.seproject.api.policy import router as policy_router
from app.seproject.indexing import index_all_scenarios
from app.seproject.scenario_pack_adapter import pack_from_persona
from app.seproject.db_models import Scenario, ScenarioPersona, ScenarioFact, RequirementsSession, Message  # noqa: F401
from app.seproject import exit_models as _exit_models  # noqa: F401 — register SQLModel tables
from app.seproject.db import configure_engine as configure_seproject_engine
from sqlmodel import SQLModel as _SESQLModel
from app.llm_registry import (
    choice_label,
    default_choice_id,
    list_llm_choices,
    ollama_reachable,
    parse_choice_id,
    resolve_llm_wrapper,
    stakeholder_llm_available,
    validate_choice_id,
)  # list_llm_choices used for BYOK model preference
from app.scenario.scenario_pack import ScenarioPack, load_scenario_pack
from app.scenario.stakeholder_prompt import STAKEHOLDER_LLM_REQUIRED_MSG
from app.security.secret_store import (
    decrypt_secret,
    encrypt_secret,
    is_unchanged_api_key,
    mask_secret,
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
    created = conversation_store.seed_users()
    if created:
        print(f"✓ Seeded users: {', '.join(created)}")
    roles = {u.username: getattr(u, "role", None) for u in conversation_store.list_users() if u.username in ("nick", "wayne", "claudine", "snick")}
    print(f"✓ Roles ready: {roles}")
    # Ensure YAML scenario + exit-interview tables exist on the shared conversation DB engine
    configure_seproject_engine(conversation_store.engine)
    _SESQLModel.metadata.create_all(conversation_store.engine)
    Path(os.getenv("STORAGE_RECORDINGS_DIR", "./storage/recordings")).mkdir(parents=True, exist_ok=True)
    seed_info = seed_scenarios(engine=conversation_store.engine)
    print(
        f"✓ YAML scenarios loaded: {seed_info['loaded']} "
        f"from {seed_info['root']} ({', '.join(seed_info['slugs']) or 'none'})"
    )
    for err in seed_info.get("errors") or []:
        print(f"⚠ Scenario load: {err}")
    index_info = index_all_scenarios(
        vector_rag=rag_systems.get("vector"),
        neo4j_rag=rag_systems.get("neo4j"),
    )
    print(
        f"✓ Indexed YAML personas into RAG: "
        f"{index_info['vector_docs']} vector docs, {index_info['neo4j_edges']} graph edges "
        f"across {index_info['packages']} packages"
    )
    yield


app = FastAPI(title="Requirements Chatbot API", lifespan=_app_lifespan)
WEB_DIR = APP_DIR / "web"
TEMPLATES_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _render_template(request: Request, name: str, context: Optional[Dict[str, Any]] = None):
    """Starlette-compatible TemplateResponse (old: name+context; new: request+name+context)."""
    import inspect

    ctx = dict(context or {})
    ctx["request"] = request
    # Bound methods omit `self` from the signature; unbound include it.
    params = [
        p
        for p in inspect.signature(templates.TemplateResponse).parameters
        if p != "self"
    ]
    # New Starlette: (request, name, context=None, ...)
    if params and params[0] == "request":
        return templates.TemplateResponse(request, name, ctx)
    # Old Starlette: (name, context, ...)
    return templates.TemplateResponse(name, ctx)


conversation_store = ConversationStore(
    os.getenv("CONVERSATION_DB_URL")
    or os.getenv("DATABASE_URL")
    or "sqlite:///./storage/conversations.db"
)
conversation_store.init()
app.state.conversation_store = conversation_store
app.state.get_current_user = _get_current_user
app.state.rag_systems = {}

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(scenarios_router)
app.include_router(admin_router)
app.include_router(teams_router, prefix="/api")
app.include_router(repositories_router, prefix="/api")
app.include_router(exit_interviews_router, prefix="/api")
app.include_router(voice_router, prefix="/api")
app.include_router(policy_router, prefix="/api")

excel_file = os.getenv("EXCEL_FILE", "data.xlsx")
print(f"Using Excel file: {excel_file}")
chroma_persist_directory = os.getenv("CHROMA_PERSIST_DIRECTORY", "./storage/chroma_db_v2")
neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
neo4j_user = os.getenv("NEO4J_USER", "neo4j")
neo4j_password = os.getenv("NEO4J_PASSWORD", "password")

rag_systems: Dict[str, Optional[object]] = {"vector": None, "neo4j": None}
engine_status: Dict[str, str] = {"vector": "not_initialized", "neo4j": "not_initialized"}
_rag_backend = os.getenv("RAG_BACKEND", "chromadb").lower()
app.state.rag_systems = rag_systems

if _rag_backend in ("chromadb", "vector", "hybrid", "compare"):
    try:
        rag_systems["vector"] = RequirementsRAG(excel_file, persist_directory=chroma_persist_directory)
        engine_status["vector"] = "ready"
        print("✓ Vector RAG (ChromaDB) initialized")
    except Exception as e:
        engine_status["vector"] = f"error: {e}"
        print(f"⚠ Vector RAG initialization failed: {e}")

if _rag_backend in ("neo4j", "hybrid", "compare"):
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

if _rag_backend == "hybrid":
    rag_systems["vector"] = rag_systems["vector"] or RequirementsRAG(excel_file, persist_directory=chroma_persist_directory)
    rag_systems["neo4j"] = rag_systems["neo4j"] or RequirementsRAGNeo4j(
        excel_file,
        neo4j_uri=neo4j_uri,
        neo4j_user=neo4j_user,
        neo4j_password=neo4j_password,
    )

llm_backend = os.getenv("LLM_BACKEND", "ollama").lower()
llm_model = os.getenv("LLM_MODEL", None)
print(f"Initializing LLM backend: {llm_backend}...")
_llm_wrappers: Dict[str, LLMWrapper] = {}
if rag_systems["vector"]:
    _llm_wrappers["vector"] = LLMWrapper(rag_systems["vector"], backend=llm_backend, model=llm_model)
if rag_systems["neo4j"]:
    _llm_wrappers["neo4j"] = LLMWrapper(rag_systems["neo4j"], backend=llm_backend, model=llm_model)
llm_by_mode: Dict[str, Optional[LLMWrapper]] = {
    "vector": _llm_wrappers.get("vector"),
    "neo4j": _llm_wrappers.get("neo4j"),
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

scenario_pack: Optional[ScenarioPack] = None
try:
    scenario_pack = load_scenario_pack(excel_file)
    print(f"✓ Scenario pack compiled ({len(scenario_pack.sections)} sections)")
except Exception as e:
    print(f"⚠ Scenario pack compilation failed: {e}")

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
                "api_key": decrypt_secret(cfg.api_key),
                "base_url": cfg.base_url,
                "scope": "user",
            }
    return {"user_providers": providers}


def _app_api_overrides() -> dict:
    """Return shared platform provider keys available to all users."""
    providers = {}
    for cfg in conversation_store.get_all_app_api_configs():
        if cfg.api_key and cfg.provider:
            plain = decrypt_secret(cfg.api_key)
            if plain:
                providers[cfg.provider.lower()] = {
                    "api_key": plain,
                    "base_url": cfg.base_url,
                    "scope": "app",
                }
    return {"app_providers": providers}


def _merged_providers_for_user(user: Optional[User]) -> dict:
    """User BYOK wins over app-wide keys for the same provider."""
    merged = {}
    merged.update(_app_api_overrides().get("app_providers", {}))
    if user:
        merged.update(_user_api_overrides(user).get("user_providers", {}))
    return merged


def _get_user_provider_override(user: Optional[User], backend: str) -> dict:
    """Get the override for a specific backend from user BYOK or app-wide keys."""
    providers = _merged_providers_for_user(user)
    info = providers.get((backend or "").lower())
    if info and info.get("api_key"):
        return {
            "provider_override": backend,
            "api_key_override": info["api_key"],
            "base_url_override": info.get("base_url"),
        }
    return {}

def _user_role(user: Optional[User]) -> str:
    if not user:
        return ROLE_STUDENT
    return normalize_role(getattr(user, "role", None), is_admin=bool(getattr(user, "is_admin", False)))


def _can_select_mode_model(user: Optional[User]) -> bool:
    """Students cannot pick mode/model; testers and admins can."""
    return _user_role(user) in (ROLE_ADMIN, ROLE_TESTER)


def _can_use_reflection(user: Optional[User]) -> bool:
    """Reflection / tweak tools are for testers and admins only."""
    return bool(user) and _user_role(user) in (ROLE_ADMIN, ROLE_TESTER)


def _require_reflection_access(request: Request) -> User:
    user = _get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if not tweak_mode_enabled or behavior_tweaks is None:
        raise HTTPException(
            status_code=403,
            detail="Tweak mode is disabled. Set TWEAK_MODE_ENABLED=true to enable reflection.",
        )
    if not _can_use_reflection(user):
        raise HTTPException(status_code=403, detail="Reflection is not available for student accounts.")
    return user


def _effective_defaults(user: Optional[User]) -> dict:
    """Resolve response mode / LLM choice defaults.

    Per-user override → role default → env fallback.
    Students cannot pick mode/model in chat, but admins may set per-user overrides.
    """
    settings = conversation_store.get_app_settings()
    role = _user_role(user) if user else ROLE_TESTER
    role_defs = conversation_store.role_defaults(role, settings)
    app_mode = (settings.default_response_mode or "vector").strip() or "vector"
    app_llm = (settings.default_llm_choice or "").strip() or None
    student_mode = (
        getattr(settings, "student_default_response_mode", None) or app_mode or "vector"
    ).strip() or "vector"
    student_llm = (getattr(settings, "student_default_llm_choice", None) or "").strip() or None
    user_mode = (getattr(user, "default_response_mode", None) or "").strip() or None if user else None
    user_llm = (getattr(user, "default_llm_choice", None) or "").strip() or None if user else None
    role_mode = role_defs.get("default_response_mode") or app_mode
    role_llm = role_defs.get("default_llm_choice") or app_llm
    return {
        "default_response_mode": user_mode or role_mode,
        "default_llm_choice": user_llm or role_llm or default_choice_id(),
        "app_default_response_mode": app_mode,
        "app_default_llm_choice": app_llm,
        "student_default_response_mode": student_mode,
        "student_default_llm_choice": student_llm,
        "role_default_response_mode": role_mode,
        "role_default_llm_choice": role_llm,
        "user_default_response_mode": user_mode,
        "user_default_llm_choice": user_llm,
        "role": role,
        "can_select_mode_model": role in (ROLE_ADMIN, ROLE_TESTER),
    }

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


def _require_stakeholder_llm(user: Optional[User]) -> None:
    providers = _merged_providers_for_user(user)
    if not stakeholder_llm_available(providers):
        raise ValueError(STAKEHOLDER_LLM_REQUIRED_MSG)


def _user_llm_provider(user: Optional[User], llm_choice: Optional[str] = None) -> str:
    """Provider name from user BYOK or app-wide keys, matching llm_choice if given."""
    providers = _merged_providers_for_user(user)
    if llm_choice:
        hint, _ = parse_choice_id(llm_choice)
        if hint and hint in providers:
            return hint
    for p in ("openai", "anthropic", "gemini", "groq", "openrouter"):
        if p in providers:
            return p
    return ""


def _available_llm_choice_ids(user: Optional[User]) -> set:
    """All selectable choice ids from Ollama + user/app providers."""
    ids: set = {c["id"] for c in list_llm_choices()}
    for provider in _merged_providers_for_user(user):
        for c in list_llm_choices(user_provider=provider):
            ids.add(c["id"])
    return ids


def _resolve_choice_for_user(user: Optional[User], llm_choice: Optional[str]) -> str:
    effective = _effective_defaults(user)
    choice = (llm_choice or "").strip() or (effective.get("default_llm_choice") or "")
    available = _available_llm_choice_ids(user)
    if choice and choice in available:
        return choice
    fallback = effective.get("default_llm_choice") or default_choice_id()
    if fallback in available:
        return fallback
    return default_choice_id()


def _resolve_llm_for_user(
    user: Optional[User],
    llm_choice: Optional[str],
    *,
    mode: str = "vector",
) -> tuple:
    """Returns (llm, resolved_choice_id, user_override dict)."""
    resolved_choice = _resolve_choice_for_user(user, llm_choice)
    backend, _ = parse_choice_id(resolved_choice)
    user_override = _get_user_provider_override(user, backend or "")
    providers = _merged_providers_for_user(user)
    user_provider = backend if backend in providers else _user_llm_provider(user, resolved_choice)
    rag = _rag_for_mode(mode) or rag_systems.get("vector") or rag_systems.get("neo4j")
    if not rag:
        raise ValueError("No RAG engine available for LLM wrapper")
    llm = resolve_llm_wrapper(rag, resolved_choice, user_provider=user_provider)
    return llm, resolved_choice, user_override
def _debug_chunks(results: Optional[List[Dict]]) -> List[Dict[str, Any]]:
    chunks: List[Dict[str, Any]] = []
    for item in (results or [])[:6]:
        meta = item.get("metadata") or {}
        doc = (item.get("document") or "").strip()
        chunks.append(
            {
                "sheet": meta.get("sheet"),
                "row": meta.get("row"),
                "backend": meta.get("backend"),
                "excerpt": doc[:240] if doc else "",
            }
        )
    return chunks


def _resolve_persona_scope(
    scenario_slug: Optional[str],
    persona_key: Optional[str],
    scenario_version: Optional[str] = None,
) -> tuple[Optional[str], Optional[str], Optional[Any]]:
    """Return (slug, persona_key, package) when YAML persona knowledge should drive RAG/direct."""
    slug = (scenario_slug or "").strip()
    persona = (persona_key or "").strip()
    if not slug or slug in ("excel", "__excel__", "powerpay"):
        return None, None, None
    if not persona:
        raise ValueError("Select a persona for the chosen YAML scenario")
    package = scenario_registry.get(slug, scenario_version)
    if package is None:
        raise ValueError(f"Scenario '{slug}' not loaded")
    if get_persona(package, persona) is None:
        raise ValueError(f"Persona '{persona}' not found in scenario '{slug}'")
    return slug, persona, package


def _generate_rag_response(
    mode: str,
    message: str,
    history: List[Dict],
    *,
    user: Optional[User] = None,
    llm_choice: Optional[str] = None,
    scenario_slug: Optional[str] = None,
    persona_key: Optional[str] = None,
) -> tuple[str, str, str, Optional[Dict[str, Any]]]:
    """Returns (response, mode_label, choice_id, debug)."""
    rag = _rag_for_mode(mode)
    if not rag:
        status = engine_status.get(mode, "unavailable")
        raise ValueError(f"Mode '{mode}' is unavailable ({status})")
    _require_stakeholder_llm(user)
    llm, resolved_choice, user_override = _resolve_llm_for_user(
        user, llm_choice, mode=mode
    )
    results = rag.search(
        message,
        n_results=llm.rag_top_k,
        filter_by_sheet_type=True,
        scenario_slug=scenario_slug,
        persona_key=persona_key,
    )
    active_pack = scenario_pack
    if scenario_slug and persona_key:
        package = scenario_registry.get(scenario_slug)
        if package is not None:
            active_pack = pack_from_persona(package, persona_key) or scenario_pack
    response = llm.generate_stakeholder_from_results(
        message,
        results,
        conversation_history=history,
        scenario_pack=active_pack,
        **user_override,
    )
    mode_label = mode
    if scenario_slug and persona_key:
        mode_label = f"{mode}:{scenario_slug}:{persona_key}"
    debug = {
        "mode": mode_label,
        "scenario_slug": scenario_slug,
        "persona_key": persona_key,
        "retrieved_chunks": _debug_chunks(results),
    }
    return response, mode_label, resolved_choice, debug


def _generate_hybrid_response(
    message: str,
    history: List[Dict],
    *,
    user: Optional[User] = None,
    llm_choice: Optional[str] = None,
    scenario_slug: Optional[str] = None,
    persona_key: Optional[str] = None,
) -> tuple[str, str, str, Dict[str, Any], Optional[Dict[str, Any]]]:
    if not hybrid_service:
        raise ValueError("Hybrid service is not initialized")
    if not rag_systems["vector"] and not rag_systems["neo4j"]:
        raise ValueError("Hybrid mode requires at least one of vector or neo4j engines")
    _require_stakeholder_llm(user)
    llm, resolved_choice, user_override = _resolve_llm_for_user(
        user, llm_choice, mode="hybrid"
    )
    handoff = hybrid_service.retrieve(
        message,
        top_k=hybrid_top_k,
        scenario_slug=scenario_slug,
        persona_key=persona_key,
    )
    active_pack = scenario_pack
    if scenario_slug and persona_key:
        package = scenario_registry.get(scenario_slug)
        if package is not None:
            active_pack = pack_from_persona(package, persona_key) or scenario_pack
    response = llm.generate_stakeholder_from_results(
        message,
        handoff.results,
        conversation_history=history,
        scenario_pack=active_pack,
        **user_override,
    )
    mode_label = f"hybrid:{handoff.route}"
    if scenario_slug and persona_key:
        mode_label = f"{mode_label}:{scenario_slug}:{persona_key}"
    routing_payload = {**handoff.routing, "backends_used": handoff.backends_used}
    debug = {
        "mode": mode_label,
        "scenario_slug": scenario_slug,
        "persona_key": persona_key,
        "retrieved_chunks": _debug_chunks(handoff.results),
        "routing": routing_payload,
    }
    return response, mode_label, resolved_choice, routing_payload, debug


def _generate_direct_response(
    message: str,
    history: List[Dict],
    *,
    user: Optional[User] = None,
    llm_choice: Optional[str] = None,
    scenario_slug: Optional[str] = None,
    persona_key: Optional[str] = None,
) -> tuple[str, str, str, Optional[Dict[str, Any]]]:
    active_pack = scenario_pack
    mode_label = "direct"
    if scenario_slug and persona_key:
        package = scenario_registry.get(scenario_slug)
        if package is None:
            raise ValueError(f"Scenario '{scenario_slug}' not loaded")
        yaml_pack = pack_from_persona(package, persona_key)
        if yaml_pack is None:
            raise ValueError(f"Persona '{persona_key}' not found in scenario '{scenario_slug}'")
        active_pack = yaml_pack
        mode_label = f"direct:{scenario_slug}:{persona_key}"
    if not active_pack:
        raise ValueError("Direct mode requires Excel data.xlsx or a YAML scenario persona")
    _require_stakeholder_llm(user)
    llm, resolved_choice, user_override = _resolve_llm_for_user(
        user, llm_choice, mode="direct"
    )
    response = llm.generate_stakeholder_direct(
        message,
        active_pack,
        conversation_history=history,
        **user_override,
    )
    debug = {
        "mode": mode_label,
        "scenario_slug": scenario_slug,
        "persona_key": persona_key,
        "scenario_sections": list(getattr(active_pack, "sections", {}).keys()),
        "retrieved_chunks": [],
    }
    return response, mode_label, resolved_choice, debug


# ── Auth endpoints ────────────────────────────────────────────

BYOK_REQUIRED_MSG = (
    "Platform token limit reached. Add your own LLM API key in Settings (⚙️) "
    "to keep chatting — usage will bill to your key, not the shared pool."
)


def _user_has_byok(user: Optional[User]) -> bool:
    if not user:
        return False
    return bool(_user_api_overrides(user).get("user_providers"))


def _quota_exhausted(user: User) -> bool:
    limit = int(getattr(user, "token_limit", 0) or 0)
    used = int(getattr(user, "tokens_used", 0) or 0)
    return limit > 0 and used >= limit


def _token_quota_payload(user: User) -> dict:
    limit = int(getattr(user, "token_limit", 0) or 0)
    used = int(getattr(user, "tokens_used", 0) or 0)
    remaining = max(0, limit - used) if limit > 0 else None
    exhausted = _quota_exhausted(user)
    has_byok = _user_has_byok(user)
    return {
        "token_limit": limit,
        "tokens_used": used,
        "tokens_remaining": remaining,
        "quota_exhausted": exhausted,
        "has_byok": has_byok,
        "billing_mode": "byok" if exhausted and has_byok else ("platform" if not exhausted else "blocked"),
    }


def _estimate_tokens(*parts: str) -> int:
    """Rough token estimate when provider usage is unavailable (~4 chars/token)."""
    total_chars = sum(len(p or "") for p in parts)
    return max(1, total_chars // 4)


def _resolve_quota_gate(user: User) -> str:
    """
    Decide how this request is billed.
    Returns 'platform' or 'byok'. Raises HTTPException if blocked.
    """
    if not _quota_exhausted(user):
        return "platform"
    if _user_has_byok(user) or ollama_reachable():
        return "byok"
    raise HTTPException(status_code=429, detail=BYOK_REQUIRED_MSG)


def _record_tokens_if_platform(
    user: User,
    *,
    billing: str,
    prompt: str,
    response: str,
    usage_tokens: int = 0,
) -> None:
    if billing != "platform":
        return
    est = usage_tokens if usage_tokens > 0 else _estimate_tokens(prompt, response)
    conversation_store.add_tokens_used(user.id, est)


def _chat_quota_fields(user: User, billing: str) -> dict:
    # Refresh usage after possible recording
    fresh = conversation_store.get_user_by_id(user.id) or user
    payload = _token_quota_payload(fresh)
    return {
        "billing": billing,
        "token_limit": payload["token_limit"],
        "tokens_used": payload["tokens_used"],
        "tokens_remaining": payload["tokens_remaining"],
    }


def _to_chat_message(m: Any) -> ChatMessage:
    created = getattr(m, "created_at", None)
    return ChatMessage(
        role=m.role,
        content=m.content,
        created_at=created.isoformat() if created is not None else None,
        mode_used=getattr(m, "mode_used", None),
    )


@app.post("/api/auth/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    user = conversation_store.get_user_by_credentials(request.username, request.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = conversation_store.create_session(user.id)
    quota = _token_quota_payload(user)
    defaults = _effective_defaults(user)
    role = defaults["role"]
    return LoginResponse(
        token=token,
        user_id=user.id,
        username=user.username,
        is_admin=role == ROLE_ADMIN,
        role=role,
        can_select_mode_model=bool(defaults["can_select_mode_model"]),
        group_name=getattr(user, "group_name", None),
        default_response_mode=defaults["default_response_mode"],
        default_llm_choice=defaults["default_llm_choice"],
        token_limit=quota["token_limit"],
        tokens_used=quota["tokens_used"],
        tokens_remaining=quota["tokens_remaining"],
        has_byok=quota["has_byok"],
        quota_exhausted=quota["quota_exhausted"],
        billing_mode=quota["billing_mode"],
    )

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
    defaults = _effective_defaults(user)
    role = defaults["role"]
    return {
        "user_id": user.id,
        "username": user.username,
        "is_admin": role == ROLE_ADMIN,
        "role": role,
        "can_select_mode_model": bool(defaults["can_select_mode_model"]),
        "group_name": getattr(user, "group_name", None),
        "default_response_mode": defaults["default_response_mode"],
        "default_llm_choice": defaults["default_llm_choice"],
        "app_default_response_mode": defaults["app_default_response_mode"],
        "app_default_llm_choice": defaults["app_default_llm_choice"],
        "student_default_response_mode": defaults.get("student_default_response_mode"),
        "student_default_llm_choice": defaults.get("student_default_llm_choice"),
        **_token_quota_payload(user),
        "byok_hint": BYOK_REQUIRED_MSG if _quota_exhausted(user) and not _user_has_byok(user) else None,
    }
# ── User API config ───────────────────────────────────────────

@app.get("/api/user/config", response_model=UserConfigGetResponse)
async def get_user_config(request: Request):
    user = _get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    all_cfgs = conversation_store.get_all_user_api_configs(user.id)
    entries = []
    for cfg in all_cfgs:
        plain = decrypt_secret(cfg.api_key) if cfg.api_key else ""
        masked = mask_secret(plain) if plain else None
        entries.append(
            ProviderKeyEntry(
                provider=cfg.provider,
                api_key_hint=masked,
                api_key_masked=masked,
                has_key=bool(plain),
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
        existing = conversation_store.get_user_api_config(user.id, entry.provider)
        if is_unchanged_api_key(entry.api_key):
            stored_key = existing.api_key if existing else ""
        elif not (entry.api_key or "").strip():
            stored_key = ""
        else:
            stored_key = encrypt_secret(entry.api_key.strip())
        conversation_store.set_user_api_config(
            user.id,
            provider=entry.provider,
            api_key=stored_key,
            base_url=entry.base_url,
        )
    return {"status": "ok"}

# ── App endpoints ─────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    user = _get_current_user(request)
    return _render_template(
        request,
        "index.html",
        {
            "authenticated": user is not None,
            "username": user.username if user else None,
            "is_admin": bool(getattr(user, "is_admin", False)) if user else False,
        },
    )


@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    user = _get_current_user(request)
    if not user:
        return _render_template(
            request,
            "admin.html",
            {"authenticated": False, "username": None, "is_admin": False},
        )
    return _render_template(
        request,
        "admin.html",
        {
            "authenticated": True,
            "username": user.username,
            "is_admin": bool(getattr(user, "is_admin", False)),
        },
    )


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, req: Request):
    user = _get_current_user(req)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        started = time.perf_counter()

        def _chat_out(**kwargs: Any) -> ChatResponse:
            return ChatResponse(
                response_ms=int((time.perf_counter() - started) * 1000),
                **kwargs,
            )

        billing = _resolve_quota_gate(user)
        # After platform quota is exhausted, require BYOK / local Ollama for LLM modes
        if billing == "byok" and not _user_has_byok(user) and not ollama_reachable():
            raise HTTPException(status_code=429, detail=BYOK_REQUIRED_MSG)

        # Students cannot choose mode/model — always use admin student defaults
        defaults = _effective_defaults(user)
        forced_mode = None
        forced_llm = None
        if not defaults.get("can_select_mode_model"):
            forced_mode = defaults.get("default_response_mode") or "vector"
            forced_llm = defaults.get("default_llm_choice")
            request.response_mode = forced_mode
            request.llm_choice = forced_llm

        conversation_id = request.conversation_id
        if conversation_id:
            convo = conversation_store.get_conversation(conversation_id)
            if not convo:
                raise ValueError(f"Conversation '{conversation_id}' not found")
            if convo.user_id != user.id:
                raise HTTPException(status_code=403, detail="Not your conversation")
        else:
            convo = conversation_store.create_conversation(
                first_prompt=request.message,
                user_id=user.id if user else 0,
                scenario_slug=request.scenario_slug,
            )
            conversation_id = convo.id

        conversation_store.add_message(conversation_id=conversation_id, role="user", content=request.message, mode_used=None)
        stored_messages = conversation_store.get_messages(conversation_id)
        history = [{"role": m.role, "content": m.content} for m in stored_messages[:-1]]
        mode = (request.response_mode or forced_mode or "vector").lower()
        user_provider = _user_llm_provider(user, request.llm_choice)
        if billing == "byok" and not user_provider and ollama_reachable():
            user_provider = "ollama"
        llm_choice = _resolve_choice_for_user(user, request.llm_choice)
        # After quota exhaustion, prefer the user's configured cloud provider when no model picked
        if billing == "byok" and user_provider and user_provider != "ollama" and not (request.llm_choice or "").strip():
            for choice in list_llm_choices(user_provider=user_provider):
                cid = str(choice.get("id") or "")
                if cid.startswith(f"{user_provider}:") and choice.get("available", True):
                    llm_choice = cid
                    break
        # Using a personal BYOK cloud key (even under quota) bills to BYOK; app-wide keys stay platform
        if billing == "platform" and user_provider and user_provider != "ollama":
            user_only = _user_api_overrides(user).get("user_providers", {})
            if user_provider in user_only:
                billing = "byok"
        debug_out: Optional[Dict[str, Any]] = None
        llm_payload = _llm_used_payload(llm_choice)
        # Scenario is locked on the conversation; persona may still change per turn
        locked_slug = (getattr(convo, "scenario_slug", None) or request.scenario_slug or "").strip() or None
        scope_slug, scope_persona, scope_package = _resolve_persona_scope(
            locked_slug,
            request.persona_key,
            request.scenario_version,
        )
        scope_kw = {"scenario_slug": scope_slug, "persona_key": scope_persona}

        if mode == "compare":
            _require_stakeholder_llm(user)
            sections: List[tuple[str, str]] = []
            compare_debug: Dict[str, Any] = {}
            resolved_choice = llm_choice

            for key, title in (
                ("vector", "Vector RAG"),
                ("neo4j", "Neo4j RAG"),
                ("hybrid", "Hybrid RAG"),
                ("direct", "Direct Model"),
            ):
                try:
                    if key == "vector":
                        resp, _, resolved_choice, dbg = _generate_rag_response(
                            "vector", request.message, history, user=user, llm_choice=llm_choice, **scope_kw
                        )
                    elif key == "neo4j":
                        resp, _, resolved_choice, dbg = _generate_rag_response(
                            "neo4j", request.message, history, user=user, llm_choice=llm_choice, **scope_kw
                        )
                    elif key == "hybrid":
                        resp, _, resolved_choice, _, dbg = _generate_hybrid_response(
                            request.message, history, user=user, llm_choice=llm_choice, **scope_kw
                        )
                    else:
                        resp, _, resolved_choice, dbg = _generate_direct_response(
                            request.message, history, user=user, llm_choice=llm_choice, **scope_kw
                        )
                    compare_debug[key] = dbg
                    sections.append((title, resp))
                except Exception as exc:
                    sections.append((title, f"[{title} unavailable: {exc}]"))

            combined = "\n\n".join(
                f"**{title}**\n{body}" for title, body in sections
            )
            conversation_store.add_message(
                conversation_id=conversation_id,
                role="assistant",
                content=combined,
                mode_used="compare",
            )
            _record_tokens_if_platform(user, billing=billing, prompt=request.message, response=combined)
            if request.debug:
                debug_out = {"compare": compare_debug}
            llm_payload = _llm_used_payload(resolved_choice or llm_choice)
            return _chat_out(
                response=combined,
                sources=None,
                mode_used="compare",
                conversation_id=conversation_id,
                llm_used=llm_payload,
                debug=debug_out,
                **_chat_quota_fields(user, billing),
            )

        if mode == "hybrid":
            response, mode_label, resolved, routing_payload, debug_out = _generate_hybrid_response(
                request.message, history, user=user, llm_choice=llm_choice, **scope_kw
            )
            conversation_store.add_message(
                conversation_id=conversation_id,
                role="assistant",
                content=response,
                mode_used=mode_label,
            )
            _record_tokens_if_platform(user, billing=billing, prompt=request.message, response=response)
            return _chat_out(
                response=response,
                sources=None,
                mode_used=mode_label,
                conversation_id=conversation_id,
                routing=routing_payload,
                llm_used=_llm_used_payload(resolved),
                debug=debug_out if request.debug else None,
                **_chat_quota_fields(user, billing),
            )

        if mode == "direct":
            response, mode_label, resolved, debug_out = _generate_direct_response(
                request.message, history, user=user, llm_choice=llm_choice, **scope_kw
            )
            conversation_store.add_message(
                conversation_id=conversation_id,
                role="assistant",
                content=response,
                mode_used=mode_label,
            )
            _record_tokens_if_platform(user, billing=billing, prompt=request.message, response=response)
            return _chat_out(
                response=response,
                sources=None,
                mode_used=mode_label,
                conversation_id=conversation_id,
                llm_used=_llm_used_payload(resolved),
                debug=debug_out if request.debug else None,
                **_chat_quota_fields(user, billing),
            )

        if mode in ("yaml", "scenario"):
            if not scope_slug or not scope_persona or scope_package is None:
                raise ValueError("YAML mode requires a YAML scenario and persona (not Excel)")
            reply = await generate_validated_reply(
                package=scope_package,
                persona_key=scope_persona,
                history=history,
                student_message=request.message,
            )
            mode_label = f"yaml:{scope_slug}:{scope_persona}"
            conversation_store.add_message(
                conversation_id=conversation_id,
                role="assistant",
                content=reply.answer,
                mode_used=mode_label,
            )
            usage_tokens = int((reply.usage or {}).get("total_tokens") or 0)
            provider = str((reply.usage or {}).get("provider") or "")
            # Heuristic / guard replies are free; only bill platform for real LLM usage
            yaml_billing = billing
            if provider in ("heuristic", "guard"):
                yaml_billing = "byok"  # skip platform metering for offline persona replies
            _record_tokens_if_platform(
                user,
                billing=yaml_billing,
                prompt=request.message,
                response=reply.answer,
                usage_tokens=usage_tokens,
            )
            yaml_debug = {
                "scenario_slug": scope_slug,
                "scenario_version": scope_package.meta.version,
                "persona_key": scope_persona,
                "used_fact_ids": reply.used_fact_ids,
                "uncertainties": reply.uncertainties,
                "handoff_suggestion": reply.handoff_suggestion,
                "model_version": reply.model_version,
            }
            return _chat_out(
                response=reply.answer,
                sources=[{"fact_id": fid} for fid in reply.used_fact_ids] or None,
                mode_used=mode_label,
                conversation_id=conversation_id,
                llm_used={
                    "provider": (reply.usage or {}).get("provider", "scenario"),
                    "model": reply.model_version,
                },
                debug=yaml_debug if request.debug else None,
                **_chat_quota_fields(user, yaml_billing if provider in ("heuristic", "guard") else billing),
            )

        if mode not in ("vector", "neo4j"):
            raise ValueError(
                "Invalid response_mode. Use: vector, neo4j, hybrid, direct, compare, or yaml"
            )

        response, mode_label, resolved, debug_out = _generate_rag_response(
            mode, request.message, history, user=user, llm_choice=llm_choice, **scope_kw
        )
        conversation_store.add_message(
            conversation_id=conversation_id,
            role="assistant",
            content=response,
            mode_used=mode_label,
        )
        _record_tokens_if_platform(user, billing=billing, prompt=request.message, response=response)
        return _chat_out(
            response=response,
            sources=None,
            mode_used=mode_label,
            conversation_id=conversation_id,
            llm_used=_llm_used_payload(resolved),
            debug=debug_out if request.debug else None,
            **_chat_quota_fields(user, billing),
        )
    except HTTPException:
        raise
    except ValueError as e:
        detail = str(e)
        status = 503 if "unavailable" in detail.lower() else 400
        if "token limit" in detail.lower() or "api key" in detail.lower():
            status = 429
        raise HTTPException(status_code=status, detail=detail)
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
            "direct": scenario_pack is not None and (
                llm_by_mode["vector"] is not None or llm_by_mode["neo4j"] is not None
            ),
            "compare": (
                scenario_pack is not None
                and (llm_by_mode["vector"] is not None or llm_by_mode["neo4j"] is not None)
            ),
            "yaml": scenario_registry.count > 0,
        },
        "engine_status": engine_status,
        "hybrid_routing": "neo4j | chroma | blend per query",
        "direct_mode": "full scenario pack in prompt (no retrieval)",
        "yaml_mode": "persona chat grounded in seproject YAML scenario packages",
        "yaml_scenarios": scenario_registry.count,
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
            scenario_slug=getattr(record, "scenario_slug", None),
            created_at=record.created_at.isoformat(),
            updated_at=record.updated_at.isoformat(),
        )
        for record in records
    ]


@app.post("/api/conversations", response_model=ConversationDetail)
async def create_conversation(body: CreateConversationRequest, request: Request):
    user = _get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    slug = (body.scenario_slug or "").strip()
    if not slug:
        raise HTTPException(status_code=400, detail="scenario_slug is required")
    package = scenario_registry.get(slug)
    if package is None:
        raise HTTPException(status_code=400, detail=f"Unknown scenario '{slug}'")
    title = (body.title or "").strip() or None
    if not title:
        pkg_title = getattr(getattr(package, "meta", None), "title", None) or slug
        title = f"{pkg_title} interview"
    convo = conversation_store.create_conversation(
        user_id=user.id,
        scenario_slug=slug,
        title=title,
    )
    return ConversationDetail(
        id=convo.id,
        title=convo.title,
        scenario_slug=convo.scenario_slug,
        created_at=convo.created_at.isoformat(),
        updated_at=convo.updated_at.isoformat(),
        messages=[],
    )


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
        scenario_slug=getattr(convo, "scenario_slug", None),
        created_at=convo.created_at.isoformat(),
        updated_at=convo.updated_at.isoformat(),
        messages=[_to_chat_message(m) for m in messages],
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
    user_providers = _user_api_overrides(user).get("user_providers", {}) if user else {}
    app_providers = _app_api_overrides().get("app_providers", {})
    merged_providers = _merged_providers_for_user(user)
    provider_names = set(merged_providers.keys())

    has_openai = "openai" in provider_names
    has_anthropic = "anthropic" in provider_names
    has_gemini = "gemini" in provider_names
    has_groq = "groq" in provider_names
    has_openrouter = "openrouter" in provider_names

    # Gather choices from Ollama + all configured user/app providers.
    # list_llm_choices()/ollama_reachable() share a short in-process Ollama tags cache.
    choices = list_llm_choices()  # base (Ollama)
    seen_ids = {c["id"] for c in choices}
    for p in ("openai", "anthropic", "gemini", "groq", "openrouter"):
        if p not in provider_names:
            continue
        scope = "user" if p in user_providers else "app"
        for c in list_llm_choices(user_provider=p):
            if c["id"] not in seen_ids:
                seen_ids.add(c["id"])
                labeled = dict(c)
                if scope == "app":
                    labeled["label"] = f"App · {c['label']}"
                    labeled["key_scope"] = "app"
                else:
                    labeled["label"] = f"Your key · {c['label']}"
                    labeled["key_scope"] = "user"
                choices.append(labeled)

    ollama_ok = ollama_reachable()
    switcher_on = (
        has_openai
        or has_anthropic
        or has_gemini
        or has_groq
        or has_openrouter
        or ollama_ok
        or len([c for c in choices if c["provider"] != "template"]) > 0
    )
    defaults = _effective_defaults(user) if user else {
        "default_response_mode": conversation_store.get_app_settings().default_response_mode or "vector",
        "default_llm_choice": conversation_store.get_app_settings().default_llm_choice or default_choice_id(),
        "app_default_response_mode": conversation_store.get_app_settings().default_response_mode or "vector",
        "app_default_llm_choice": conversation_store.get_app_settings().default_llm_choice,
        "role": ROLE_STUDENT,
        "can_select_mode_model": False,
    }
    can_select = bool(defaults.get("can_select_mode_model")) if user else False
    return {
        "excel_file": excel_file,
        "neo4j_uri": neo4j_uri,
        "engines": engine_status,
        "llm_backend_env": llm_backend,
        "llm_model_env": llm_model,
        "llm_default_choice": defaults.get("default_llm_choice") or default_choice_id(),
        "default_response_mode": defaults.get("default_response_mode") or "vector",
        "app_default_response_mode": defaults.get("app_default_response_mode"),
        "app_default_llm_choice": defaults.get("app_default_llm_choice"),
        "student_default_response_mode": defaults.get("student_default_response_mode"),
        "student_default_llm_choice": defaults.get("student_default_llm_choice"),
        "llm_choices": choices if can_select else [],
        "llm_model_switcher_enabled": can_select and switcher_on and len(choices) > 1,
        "can_select_mode_model": can_select,
        "role": defaults.get("role") or _user_role(user),
        "llm_providers": {
            "openai": has_openai,
            "anthropic": has_anthropic,
            "gemini": has_gemini,
            "groq": has_groq,
            "openrouter": has_openrouter,
            "ollama": ollama_ok,
        },
        "app_key_providers": sorted(app_providers.keys()),
        "hybrid_top_k": hybrid_top_k,
        "hybrid_route_margin": hybrid_route_margin,
        "tweak_mode_enabled": bool(
            tweak_mode_enabled and (not user or _can_use_reflection(user))
        ),
        "reflection_enabled": bool(
            tweak_mode_enabled and user and _can_use_reflection(user)
        ),
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
        "is_admin": (_user_role(user) == ROLE_ADMIN) if user else False,
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
        messages=[_to_chat_message(m) for m in messages],
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
    _require_reflection_access(req)
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
    _require_reflection_access(request)
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
    _require_reflection_access(request)
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
    _require_reflection_access(request)
    return _thread_to_detail(thread_id)


@app.post("/api/reflections/{thread_id}/chat")
async def chat_reflection_thread(thread_id: str, request: ReflectionThreadChatRequest, req: Request):
    _require_reflection_access(req)
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
    _require_reflection_access(req)
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
    _require_reflection_access(req)
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
    _require_reflection_access(req)
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

# Exit-interview React SPA (built with vite base=/course/)
COURSE_DIST = _PROJECT_ROOT / "frontend" / "dist"
COURSE_ASSETS = COURSE_DIST / "assets"
if COURSE_ASSETS.is_dir():
    app.mount("/course/assets", StaticFiles(directory=str(COURSE_ASSETS)), name="course-assets")


@app.get("/course")
async def course_root_redirect():
    return RedirectResponse(url="/course/")


@app.get("/course/")
@app.get("/course/{full_path:path}")
async def course_spa(full_path: str = ""):
    if not COURSE_DIST.is_dir():
        raise HTTPException(
            status_code=404,
            detail="Course SPA not built. Run: cd frontend && npm ci && npm run build",
        )
    if full_path:
        candidate = (COURSE_DIST / full_path).resolve()
        try:
            candidate.relative_to(COURSE_DIST.resolve())
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="Not found") from exc
        if candidate.is_file():
            return FileResponse(candidate)
    index = COURSE_DIST / "index.html"
    if not index.is_file():
        raise HTTPException(status_code=404, detail="Course SPA index missing")
    return FileResponse(index)

