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
        print(f"✓ Loaded environment variables from {_app_env}")
    elif _root_env.is_file():
        print(f"✓ Loaded environment variables from {_root_env}")
    else:
        print(f"⚠ No {_app_env} or {_root_env} — using OS env and cwd .env if any")
except ImportError:
    print("⚠ python-dotenv not installed. Install with: pip install python-dotenv")
    print("  Continuing without .env file support...")
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api.schemas import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    ConversationDetail,
    ConversationSummary,
    FeedbackRequest,
    ReflectionAnalyzeRequest,
    ReflectionApplyRequest,
    ReflectionThreadChatRequest,
    ReflectionThreadDetail,
    ReflectionThreadStartResponse,
    ReflectionThreadSummary,
)
from app.storage.conversation_store import ConversationStore
from app.tweaks.behavior_tweaks import BehaviorTweaksStore
from app.llm_wrapper import LLMWrapper
from app.rag_backend import RequirementsRAG
from app.rag_backend_neo4j import RequirementsRAGNeo4j
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

app = FastAPI(title="Requirements Chatbot API")
WEB_DIR = APP_DIR / "web"
TEMPLATES_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
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


def _generate_mode_response(mode: str, message: str, history: List[Dict]) -> str:
    llm = llm_by_mode.get(mode)
    if not llm:
        status = engine_status.get(mode, "unavailable")
        raise ValueError(f"Mode '{mode}' is unavailable ({status})")
    return llm.generate_response(
        message,
        conversation_history=history,
        behavior_system_suffix=_behavior_system_suffix(),
    )


def _apply_runtime_tweaks(query: str, response: str) -> str:
    if not tweak_mode_enabled or behavior_tweaks is None:
        return response
    return behavior_tweaks.apply_to_response(query, response)


def _merge_hybrid_results(message: str) -> List[Dict]:
    if not rag_systems["vector"] or not rag_systems["neo4j"]:
        raise ValueError("Hybrid mode requires both vector and neo4j engines")

    vector_results = rag_systems["vector"].search(message, n_results=hybrid_top_k, filter_by_sheet_type=True)
    neo4j_results = rag_systems["neo4j"].search(message, n_results=hybrid_top_k, filter_by_sheet_type=True)
    merged: List[Dict] = []
    seen_docs = set()
    for idx in range(max(len(vector_results), len(neo4j_results))):
        if idx < len(vector_results):
            doc = vector_results[idx].get("document", "")
            if doc and doc not in seen_docs:
                merged.append(vector_results[idx])
                seen_docs.add(doc)
        if idx < len(neo4j_results):
            doc = neo4j_results[idx].get("document", "")
            if doc and doc not in seen_docs:
                merged.append(neo4j_results[idx])
                seen_docs.add(doc)
    return merged


@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    try:
        conversation_id = request.conversation_id
        if conversation_id:
            convo = conversation_store.get_conversation(conversation_id)
            if not convo:
                raise ValueError(f"Conversation '{conversation_id}' not found")
        else:
            convo = conversation_store.create_conversation(first_prompt=request.message)
            conversation_id = convo.id

        conversation_store.add_message(conversation_id=conversation_id, role="user", content=request.message, mode_used=None)
        stored_messages = conversation_store.get_messages(conversation_id)
        history = [{"role": m.role, "content": m.content} for m in stored_messages[:-1]]
        mode = (request.response_mode or "vector").lower()

        if mode == "compare":
            vector_response = _apply_runtime_tweaks(request.message, _generate_mode_response("vector", request.message, history))
            neo4j_response = _apply_runtime_tweaks(request.message, _generate_mode_response("neo4j", request.message, history))
            combined = (
                "<strong>Vector RAG (Embeddings + ChromaDB)</strong><br>"
                f"{vector_response}<br><br>"
                "<strong>Neo4j Structured RAG</strong><br>"
                f"{neo4j_response}"
            )
            conversation_store.add_message(conversation_id=conversation_id, role="assistant", content=combined, mode_used="compare")
            return ChatResponse(response=combined, sources=None, mode_used="compare", conversation_id=conversation_id)

        if mode == "hybrid":
            base_llm = llm_by_mode.get("vector") or llm_by_mode.get("neo4j")
            if not base_llm:
                raise ValueError("Hybrid mode is unavailable because no LLM wrapper is ready")
            merged_results = _merge_hybrid_results(request.message)
            response = base_llm.generate_response_from_results(
                request.message,
                merged_results,
                conversation_history=history,
                behavior_system_suffix=_behavior_system_suffix(),
            )
            response = _apply_runtime_tweaks(request.message, response)
            conversation_store.add_message(conversation_id=conversation_id, role="assistant", content=response, mode_used="hybrid")
            return ChatResponse(response=response, sources=None, mode_used="hybrid", conversation_id=conversation_id)

        if mode not in ("vector", "neo4j"):
            raise ValueError("Invalid response_mode. Use: vector, neo4j, hybrid, or compare")

        response = _apply_runtime_tweaks(request.message, _generate_mode_response(mode, request.message, history))
        conversation_store.add_message(conversation_id=conversation_id, role="assistant", content=response, mode_used=mode)
        return ChatResponse(response=response, sources=None, mode_used=mode, conversation_id=conversation_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/health")
async def health():
    try:
        doc_counts = {}
        doc_counts["vector"] = rag_systems["vector"].collection.count() if rag_systems["vector"] and hasattr(rag_systems["vector"], "collection") else 0
        doc_counts["neo4j"] = rag_systems["neo4j"]._count_nodes() if rag_systems["neo4j"] and hasattr(rag_systems["neo4j"], "_count_nodes") else 0
        return {"status": "healthy", "engines": engine_status, "documents": doc_counts}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.get("/api/modes")
async def modes():
    return {
        "available_modes": {
            "vector": llm_by_mode["vector"] is not None,
            "neo4j": llm_by_mode["neo4j"] is not None,
            "hybrid": (llm_by_mode["vector"] is not None and llm_by_mode["neo4j"] is not None),
            "compare": (llm_by_mode["vector"] is not None and llm_by_mode["neo4j"] is not None),
        },
        "engine_status": engine_status,
    }


@app.get("/api/conversations", response_model=List[ConversationSummary])
async def list_conversations():
    records = conversation_store.list_conversations(limit=100)
    return [
        ConversationSummary(
            id=record.id,
            title=record.title,
            created_at=record.created_at.isoformat(),
            updated_at=record.updated_at.isoformat(),
        )
        for record in records
    ]


@app.get("/api/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(conversation_id: str):
    convo = conversation_store.get_conversation(conversation_id)
    if not convo:
        raise HTTPException(status_code=404, detail="Conversation not found")
    messages = conversation_store.get_messages(conversation_id)
    return ConversationDetail(
        id=convo.id,
        title=convo.title,
        created_at=convo.created_at.isoformat(),
        updated_at=convo.updated_at.isoformat(),
        messages=[ChatMessage(role=m.role, content=m.content) for m in messages],
    )


@app.get("/api/config")
async def config():
    openai_key = os.getenv("OPENAI_API_KEY")
    openai_key_status = "present" if openai_key else "missing"
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
    return {
        "excel_file": excel_file,
        "neo4j_uri": neo4j_uri,
        "engines": engine_status,
        "llm_backend_env": llm_backend,
        "llm_model_env": llm_model,
        "hybrid_top_k": hybrid_top_k,
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
        "openai_api_key_status": openai_key_status,
        "openai_api_key_hint": (f"{openai_key[:7]}...{openai_key[-4:]}" if openai_key and len(openai_key) > 12 else None),
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
async def reflection_analyze(request: ReflectionAnalyzeRequest):
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
async def list_reflection_threads(conversation_id: str):
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
async def start_reflection_thread(conversation_id: str):
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
async def get_reflection_thread(thread_id: str):
    return _thread_to_detail(thread_id)


@app.post("/api/reflections/{thread_id}/chat")
async def chat_reflection_thread(thread_id: str, request: ReflectionThreadChatRequest):
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
async def apply_reflection_thread(thread_id: str, request: ReflectionApplyRequest):
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
async def reflection_apply(request: ReflectionApplyRequest):
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
async def feedback(request: FeedbackRequest):
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

