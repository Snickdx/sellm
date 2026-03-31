"""Pydantic schemas for API requests/responses."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    conversation_history: Optional[List[ChatMessage]] = []
    response_mode: Optional[str] = "vector"
    conversation_id: Optional[str] = None


class ChatResponse(BaseModel):
    response: str
    sources: Optional[List[dict]] = None
    mode_used: Optional[str] = None
    conversation_id: Optional[str] = None


class FeedbackRequest(BaseModel):
    prompt: str
    response: str
    feedback: str
    mode_used: Optional[str] = None
    desired_response: Optional[str] = None


class ConversationSummary(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str


class ConversationDetail(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str
    messages: List[ChatMessage]


class ReflectionAnalyzeRequest(BaseModel):
    """Send stored conversation id and/or inline messages (UI transcript)."""

    conversation_id: Optional[str] = None
    messages: Optional[List[ChatMessage]] = None


class ReflectionApplyRequest(BaseModel):
    """Payload returned from analyze (normalized), applied after user confirms."""

    reflection: Dict[str, Any]


class ReflectionThreadSummary(BaseModel):
    id: str
    conversation_id: str
    title: str
    created_at: str
    updated_at: str


class ReflectionThreadDetail(BaseModel):
    id: str
    conversation_id: str
    title: str
    latest_draft_json: Optional[str] = None
    created_at: str
    updated_at: str
    messages: List[ChatMessage]


class ReflectionThreadStartResponse(BaseModel):
    thread: ReflectionThreadDetail
    reflection: Dict[str, Any]
    mode_used: str


class ReflectionThreadChatRequest(BaseModel):
    message: str
    reflection: Optional[Dict[str, Any]] = None

