"""Unified stakeholder simulation prompt for all chat modes."""

from __future__ import annotations

from typing import Dict, List, Optional

STAKEHOLDER_LLM_REQUIRED_MSG = (
    "Stakeholder simulation requires a configured LLM backend. "
    "Please configure Ollama, OpenAI, Anthropic, Groq, or OpenRouter."
)

STAKEHOLDER_SYSTEM_PROMPT = """You are role-playing a non-technical stakeholder in a requirements elicitation interview.

You know the project context provided to you, but you must not sound like you are reading from a document.

Answer only as this stakeholder would answer.
Use natural, informal language.
Answer the trainee's actual question directly.
Do not mention requirements documents, spreadsheets, rows, source data, embeddings, graph databases, vector search, retrieval, or internal IDs.
Do not volunteer every related fact at once.
If the trainee asks a broad question, answer broadly and leave room for follow-up.
If the trainee asks a specific question, answer that specific question first.
If the stakeholder would not know something, say so.
If the trainee uses technical terminology, respond in plain business language.
Stay in character at all times.
Keep answers concise unless the user asks for detail.
Use the conversation history to avoid repeating yourself."""


def format_conversation_history(
    conversation_history: Optional[List[Dict]], *, max_turns: int = 8
) -> str:
    if not conversation_history:
        return "No prior conversation."
    lines = []
    for turn in conversation_history[-max_turns:]:
        role = turn.get("role", "user")
        content = (turn.get("content") or "").strip()
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines) if lines else "No prior conversation."


def format_retrieved_context(results: List[dict], *, max_items: int = 6) -> str:
    """Format RAG hits as supporting notes (no sheet/row labels for the model to echo)."""
    blocks: List[str] = []
    for result in results[:max_items]:
        doc = (result.get("document") or "").strip()
        if not doc:
            continue
        lines = doc.split("\n")
        parts: List[str] = []
        for line in lines:
            if line.lower().startswith("sheet:"):
                continue
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            value = value.strip()
            if value and value.lower() not in ("nan", "none", ""):
                parts.append(f"{key.strip()}: {value}")
        if parts:
            blocks.append(" · ".join(parts[:10]))
    if not blocks:
        return "No specific supporting details were retrieved for this question."
    return "\n".join(f"- {block}" for block in blocks)


def build_stakeholder_user_message(
    query: str,
    *,
    context_block: str,
    conversation_history: Optional[List[Dict]] = None,
    context_label: str = "Supporting project context",
) -> str:
    history_text = format_conversation_history(conversation_history)
    return f"""{context_label} (use as background knowledge — do not quote it verbatim or list everything):
{context_block}

Recent conversation:
{history_text}

Trainee question: {query}

Reply in character as the stakeholder. Answer the question directly."""
