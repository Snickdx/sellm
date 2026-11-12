"""Pydantic schemas for API requests/responses."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str
    created_at: Optional[str] = None
    mode_used: Optional[str] = None


class ChatRequest(BaseModel):
    message: str
    conversation_history: Optional[List[ChatMessage]] = []
    response_mode: Optional[str] = "vector"
    conversation_id: Optional[str] = None
    llm_choice: Optional[str] = None  # e.g. openai:gpt-4o-mini, ollama:llama3.2
    debug: Optional[bool] = False  # include retrieval/routing metadata for instructors
    # YAML scenario mode (peer to vector / neo4j)
    scenario_slug: Optional[str] = None
    scenario_version: Optional[str] = None
    persona_key: Optional[str] = None


class ChatResponse(BaseModel):
    response: str
    sources: Optional[List[dict]] = None
    mode_used: Optional[str] = None
    conversation_id: Optional[str] = None
    routing: Optional[Dict[str, Any]] = None
    llm_used: Optional[Dict[str, Any]] = None
    debug: Optional[Dict[str, Any]] = None
    billing: Optional[str] = None  # platform | byok
    token_limit: Optional[int] = None
    tokens_used: Optional[int] = None
    tokens_remaining: Optional[int] = None
    response_ms: Optional[int] = None


class FeedbackRequest(BaseModel):
    prompt: str
    response: str
    feedback: str
    mode_used: Optional[str] = None
    desired_response: Optional[str] = None


class CreateConversationRequest(BaseModel):
    scenario_slug: Optional[str] = None
    title: Optional[str] = None


class ConversationSummary(BaseModel):
    id: str
    title: str
    scenario_slug: Optional[str] = None
    created_at: str
    updated_at: str


class ConversationDetail(BaseModel):
    id: str
    title: str
    scenario_slug: Optional[str] = None
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


# ── Auth ──────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str

class LoginResponse(BaseModel):
    token: str
    user_id: int
    username: str
    is_admin: Optional[bool] = False
    role: Optional[str] = None  # admin | tester | student
    can_select_mode_model: Optional[bool] = True
    group_name: Optional[str] = None
    default_response_mode: Optional[str] = None
    default_llm_choice: Optional[str] = None
    token_limit: Optional[int] = None
    tokens_used: Optional[int] = None
    tokens_remaining: Optional[int] = None
    has_byok: Optional[bool] = None
    quota_exhausted: Optional[bool] = None
    billing_mode: Optional[str] = None  # platform | byok

class ProviderKeyEntry(BaseModel):
    provider: str
    api_key_hint: Optional[str] = None
    api_key_masked: Optional[str] = None
    has_key: bool = False
    base_url: Optional[str] = None
    scope: Optional[str] = None  # user | app

class UserConfigGetResponse(BaseModel):
    keys: List[ProviderKeyEntry] = []

class UserConfigProviderSet(BaseModel):
    provider: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None

class UserConfigSetRequest(BaseModel):
    keys: List[UserConfigProviderSet] = []


# ── Admin ─────────────────────────────────────────────────────

class AdminUserSummary(BaseModel):
    id: int
    username: str
    is_admin: bool = False
    role: str = "student"
    can_select_mode_model: bool = False
    group_name: Optional[str] = None
    admin_notes: Optional[str] = None
    token_limit: int = 0
    tokens_used: int = 0
    tokens_remaining: Optional[int] = None
    budget_is_override: bool = False
    default_response_mode: Optional[str] = None
    default_llm_choice: Optional[str] = None
    mode_is_override: bool = False
    llm_is_override: bool = False
    role_default_response_mode: Optional[str] = None
    role_default_llm_choice: Optional[str] = None
    role_token_limit: int = 0
    effective_response_mode: Optional[str] = None
    effective_llm_choice: Optional[str] = None
    conversation_count: int = 0
    created_at: str


class AdminUserCreateRequest(BaseModel):
    username: str
    password: str
    token_limit: Optional[int] = None
    budget_is_override: Optional[bool] = None
    is_admin: bool = False
    role: Optional[str] = None  # admin | tester | student
    group_name: Optional[str] = None
    admin_notes: Optional[str] = None
    default_response_mode: Optional[str] = None
    default_llm_choice: Optional[str] = None


class AdminUserUpdateRequest(BaseModel):
    token_limit: Optional[int] = None
    tokens_used: Optional[int] = None
    reset_tokens: Optional[bool] = None
    is_admin: Optional[bool] = None
    role: Optional[str] = None
    group_name: Optional[str] = None
    clear_group: Optional[bool] = None
    admin_notes: Optional[str] = None
    default_response_mode: Optional[str] = None
    clear_default_response_mode: Optional[bool] = None
    default_llm_choice: Optional[str] = None
    clear_default_llm_choice: Optional[bool] = None
    budget_is_override: Optional[bool] = None
    reset_budget_to_role: Optional[bool] = None
    reset_mode_to_role: Optional[bool] = None
    reset_llm_to_role: Optional[bool] = None
    reset_defaults_to_role: Optional[bool] = None
    password: Optional[str] = None


class AdminUserDeleteRequest(BaseModel):
    user_ids: List[int]


class AdminUserDeleteResult(BaseModel):
    deleted: List[int]
    skipped: List[int] = []
    failed: List[dict] = []


class AdminConversationSummary(BaseModel):
    id: str
    title: str
    scenario_slug: Optional[str] = None
    message_count: int = 0
    created_at: str
    updated_at: str


class AdminConversationDetail(BaseModel):
    id: str
    title: str
    scenario_slug: Optional[str] = None
    user_id: int
    username: str
    created_at: str
    updated_at: str
    messages: List[ChatMessage]


class AdminAppSettings(BaseModel):
    default_response_mode: str = "vector"
    default_llm_choice: Optional[str] = None
    tester_token_limit: int = 15000
    student_default_response_mode: str = "vector"
    student_default_llm_choice: Optional[str] = None
    student_token_limit: int = 15000
    admin_default_response_mode: Optional[str] = None
    admin_default_llm_choice: Optional[str] = None
    admin_token_limit: int = 50000
    updated_at: Optional[str] = None


class AdminAppSettingsUpdate(BaseModel):
    default_response_mode: Optional[str] = None
    default_llm_choice: Optional[str] = None
    clear_default_llm_choice: Optional[bool] = None
    tester_token_limit: Optional[int] = None
    student_default_response_mode: Optional[str] = None
    student_default_llm_choice: Optional[str] = None
    clear_student_default_llm_choice: Optional[bool] = None
    student_token_limit: Optional[int] = None
    admin_default_response_mode: Optional[str] = None
    clear_admin_default_response_mode: Optional[bool] = None
    admin_default_llm_choice: Optional[str] = None
    clear_admin_default_llm_choice: Optional[bool] = None
    admin_token_limit: Optional[int] = None
    apply_budgets: Optional[bool] = True


class AdminAppKeysGetResponse(BaseModel):
    keys: List[ProviderKeyEntry] = []


class AdminAppKeysSetRequest(BaseModel):
    keys: List[UserConfigProviderSet] = []


class AdminTokenSummary(BaseModel):
    user_count: int
    total_token_limit: int
    total_tokens_used: int
    exhausted_users: int
    by_group: Dict[str, Dict[str, int]]
    users: List[AdminUserSummary]

