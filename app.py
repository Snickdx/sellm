"""
FastAPI backend for Requirements Chatbot
"""
# Apply pytree compatibility fix
try:
    import fix_pytree
except ImportError:
    pass

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("✓ Loaded environment variables from .env file")
except ImportError:
    print("⚠ python-dotenv not installed. Install with: pip install python-dotenv")
    print("  Continuing without .env file support...")

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Dict, List, Optional
import os
from rag_backend import RequirementsRAG
from llm_wrapper import LLMWrapper
from behavior_tweaks import BehaviorTweaksStore

app = FastAPI(title="Requirements Chatbot API")

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Get Excel file name from environment variable
excel_file = os.getenv("EXCEL_FILE", "data.xlsx")
print(f"Using Excel file: {excel_file}")

neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
neo4j_user = os.getenv("NEO4J_USER", "neo4j")
neo4j_password = os.getenv("NEO4J_PASSWORD", "password")

print("Initializing RAG systems for comparison...")
rag_systems: Dict[str, Optional[object]] = {"vector": None, "neo4j": None}
engine_status: Dict[str, str] = {
    "vector": "not_initialized",
    "neo4j": "not_initialized",
}

try:
    rag_systems["vector"] = RequirementsRAG(excel_file)
    engine_status["vector"] = "ready"
    print("✓ Vector RAG (ChromaDB) initialized")
except Exception as e:
    engine_status["vector"] = f"error: {e}"
    print(f"⚠ Vector RAG initialization failed: {e}")

try:
    from rag_backend_neo4j import RequirementsRAGNeo4j

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
    print("⚠ Neo4j backend not available (package missing)")
except Exception as e:
    engine_status["neo4j"] = f"error: {e}"
    print(f"⚠ Neo4j initialization failed: {e}")

# Initialize LLM (try Ollama first, fallback to template)
# Set LLM_BACKEND env var to "ollama", "openai", or "template"
# Set LLM_MODEL env var to specify model (e.g., "llama3.2", "mistral")
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
tweak_mode_enabled = os.getenv("TWEAK_MODE_ENABLED", "false").strip().lower() in ("1", "true", "yes", "on")
behavior_tweaks_file = os.getenv("BEHAVIOR_TWEAKS_FILE", "behavior_tweaks.json")
behavior_tweaks = BehaviorTweaksStore(behavior_tweaks_file) if tweak_mode_enabled else None
print("RAG system ready!")


class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    conversation_history: Optional[List[ChatMessage]] = []
    response_mode: Optional[str] = "vector"


class ChatResponse(BaseModel):
    response: str
    sources: Optional[List[dict]] = None
    mode_used: Optional[str] = None


class FeedbackRequest(BaseModel):
    prompt: str
    response: str
    feedback: str
    mode_used: Optional[str] = None
    desired_response: Optional[str] = None


def _generate_mode_response(mode: str, message: str, history: List[Dict]) -> str:
    llm = llm_by_mode.get(mode)
    if not llm:
        status = engine_status.get(mode, "unavailable")
        raise ValueError(f"Mode '{mode}' is unavailable ({status})")
    return llm.generate_response(message, conversation_history=history)


def _apply_runtime_tweaks(query: str, response: str) -> str:
    if not tweak_mode_enabled or behavior_tweaks is None:
        return response
    return behavior_tweaks.apply_to_response(query, response)


def _merge_hybrid_results(message: str) -> List[Dict]:
    """Interleave top results from vector and neo4j retrieval paths."""
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


@app.get("/")
async def read_root():
    """Serve the chat UI"""
    return FileResponse("index.html")


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Handle chat messages"""
    try:
        # Convert pydantic chat history to dicts for prompt construction.
        history = [
            {"role": msg.role, "content": msg.content}
            for msg in (request.conversation_history or [])
        ]
        mode = (request.response_mode or "vector").lower()

        if mode == "compare":
            vector_response = _generate_mode_response("vector", request.message, history)
            neo4j_response = _generate_mode_response("neo4j", request.message, history)
            vector_response = _apply_runtime_tweaks(request.message, vector_response)
            neo4j_response = _apply_runtime_tweaks(request.message, neo4j_response)
            combined = (
                "<strong>Vector RAG (Embeddings + ChromaDB)</strong><br>"
                f"{vector_response}<br><br>"
                "<strong>Neo4j Structured RAG</strong><br>"
                f"{neo4j_response}"
            )
            return ChatResponse(response=combined, sources=None, mode_used="compare")

        if mode == "hybrid":
            base_llm = llm_by_mode.get("vector") or llm_by_mode.get("neo4j")
            if not base_llm:
                raise ValueError("Hybrid mode is unavailable because no LLM wrapper is ready")
            merged_results = _merge_hybrid_results(request.message)
            response = base_llm.generate_response_from_results(
                request.message,
                merged_results,
                conversation_history=history,
            )
            response = _apply_runtime_tweaks(request.message, response)
            return ChatResponse(response=response, sources=None, mode_used="hybrid")

        if mode not in ("vector", "neo4j"):
            raise ValueError("Invalid response_mode. Use: vector, neo4j, hybrid, or compare")

        response = _generate_mode_response(mode, request.message, history)
        response = _apply_runtime_tweaks(request.message, response)
        return ChatResponse(response=response, sources=None, mode_used=mode)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/health")
async def health():
    """Health check endpoint"""
    try:
        doc_counts = {}
        if rag_systems["vector"] and hasattr(rag_systems["vector"], "collection"):
            doc_counts["vector"] = rag_systems["vector"].collection.count()
        else:
            doc_counts["vector"] = 0

        if rag_systems["neo4j"] and hasattr(rag_systems["neo4j"], "_count_nodes"):
            doc_counts["neo4j"] = rag_systems["neo4j"]._count_nodes()
        else:
            doc_counts["neo4j"] = 0

        return {
            "status": "healthy",
            "engines": engine_status,
            "documents": doc_counts
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }


@app.get("/api/modes")
async def modes():
    """Return available response generation modes."""
    return {
        "available_modes": {
            "vector": llm_by_mode["vector"] is not None,
            "neo4j": llm_by_mode["neo4j"] is not None,
            "hybrid": (llm_by_mode["vector"] is not None and llm_by_mode["neo4j"] is not None),
            "compare": (llm_by_mode["vector"] is not None and llm_by_mode["neo4j"] is not None),
        },
        "engine_status": engine_status,
    }


@app.get("/api/config")
async def config():
    """Return current runtime config and key status (without exposing secrets)."""
    openai_key = os.getenv("OPENAI_API_KEY")
    openai_key_status = "missing"
    if openai_key:
        openai_key_status = "present"

    active_wrappers = {
        mode: wrapper for mode, wrapper in llm_by_mode.items() if wrapper is not None
    }

    llm_runtime = {}
    for mode, wrapper in active_wrappers.items():
        llm_runtime[mode] = {
            "backend": wrapper.backend,
            "model": wrapper.model,
            "temperature": wrapper.temperature,
            "max_tokens": wrapper.max_tokens,
            "rag_top_k": wrapper.rag_top_k,
        }

    return {
        "excel_file": excel_file,
        "neo4j_uri": neo4j_uri,
        "engines": engine_status,
        "llm_backend_env": llm_backend,
        "llm_model_env": llm_model,
        "hybrid_top_k": hybrid_top_k,
        "tweak_mode_enabled": tweak_mode_enabled,
        "behavior_tweaks_file": behavior_tweaks_file,
        "behavior_tweaks_last_updated": (
            behavior_tweaks.load().get("last_updated") if behavior_tweaks else None
        ),
        "openai_api_key_status": openai_key_status,
        "openai_api_key_hint": (
            f"{openai_key[:7]}...{openai_key[-4:]}" if openai_key and len(openai_key) > 12 else None
        ),
        "llm_runtime_by_mode": llm_runtime,
    }


@app.post("/api/feedback")
async def feedback(request: FeedbackRequest):
    """Capture response feedback and update runtime behavior tweaks."""
    if not tweak_mode_enabled or behavior_tweaks is None:
        raise HTTPException(
            status_code=403,
            detail="Tweak mode is disabled. Set TWEAK_MODE_ENABLED=true to enable feedback loop.",
        )
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


# Serve static files
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
