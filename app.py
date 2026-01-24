"""
FastAPI backend for Requirements Chatbot
"""
# Apply pytree compatibility fix
try:
    import fix_pytree
except ImportError:
    pass

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional
import os
from rag_backend import RequirementsRAG, SimpleLLM

app = FastAPI(title="Requirements Chatbot API")

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize RAG system
print("Initializing RAG system...")
rag_system = RequirementsRAG("graph_model_nicholas (1).xlsx")
llm = SimpleLLM(rag_system)
print("RAG system ready!")


class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    conversation_history: Optional[List[ChatMessage]] = []


class ChatResponse(BaseModel):
    response: str
    sources: Optional[List[dict]] = None


@app.get("/")
async def read_root():
    """Serve the chat UI"""
    return FileResponse("index.html")


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Handle chat messages"""
    try:
        # Get relevant context
        search_results = rag_system.search(request.message, n_results=3)
        
        # Generate response (simple template-based for now)
        # In production, you'd use an actual LLM here
        context = rag_system.get_context(request.message, n_results=3)
        
        # Generate intelligent response using the improved LLM
        response = llm.generate_response(request.message)
        
        # Don't return sources - this is a training simulation, not a document query system
        # The user should formalize requirements from the conversation, not see source references
        return ChatResponse(response=response, sources=None)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "documents": rag_system.collection.count()
    }


# Serve static files
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
