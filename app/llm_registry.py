"""Discover configured LLM providers/models and cache LLMWrapper instances."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple  # noqa: F401 used by stakeholder_llm_available

from app.llm_wrapper import LLMWrapper

OPENAI_DEFAULT_MODELS = [
    "gpt-4o-mini",
    "gpt-4o",
    "gpt-4-turbo",
    "gpt-4",
    "gpt-3.5-turbo",
    "o1-mini",
]

OLLAMA_FALLBACK_MODELS = ["llama3.2", "mistral", "phi3", "gemma2", "llama3.1"]

_wrapper_cache: Dict[Tuple[int, str, str], LLMWrapper] = {}


def _parse_csv_env(name: str) -> List[str]:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


def ollama_host() -> str:
    return (os.getenv("OLLAMA_HOST") or "http://localhost:11434").rstrip("/")


def fetch_ollama_tags() -> List[str]:
    """Full model tags from Ollama (e.g. llama3.2:latest)."""
    try:
        import requests

        response = requests.get(f"{ollama_host()}/api/tags", timeout=2)
        if response.status_code != 200:
            return []
        names: List[str] = []
        for item in response.json().get("models", []):
            raw = (item.get("name") or "").strip()
            if raw:
                names.append(raw)
        return names
    except Exception:
        return []


def fetch_ollama_model_names() -> List[str]:
    """Base model names for UI labels (llama3.2, gemma4, …)."""
    bases = []
    for tag in fetch_ollama_tags():
        base = tag.split(":")[0]
        if base and base not in bases:
            bases.append(base)
    return sorted(bases)


def _pick_ollama_tag(tags: List[str], base_hint: Optional[str] = None) -> str:
    """Choose best installed tag using env/default preferences."""
    hints: List[str] = []
    if base_hint:
        hints.append(base_hint.split(":")[0])
    env_model = (os.getenv("LLM_MODEL") or "").strip()
    if env_model:
        hints.append(env_model.split(":")[0])
    hints.extend(["llama3.2", "llama3.1", "gemma4", "mistral", "phi3", "llama2"])
    seen: set[str] = set()
    for base in hints:
        if not base or base in seen:
            continue
        seen.add(base)
        for tag in tags:
            if tag.split(":")[0] == base:
                return tag
    return tags[0]


def resolve_ollama_model(requested: Optional[str]) -> Optional[str]:
    """Map config/UI name to an installed Ollama tag; avoids 404 on missing models."""
    tags = fetch_ollama_tags()
    if not tags:
        return (requested or "").strip() or None
    if not requested:
        return _pick_ollama_tag(tags)
    req = requested.strip()
    if req in tags:
        return req
    base = req.split(":")[0]
    for tag in tags:
        if tag.split(":")[0] == base:
            return tag
    return _pick_ollama_tag(tags, base_hint=base)


def ollama_reachable() -> bool:
    return bool(fetch_ollama_tags())


def openai_configured() -> bool:
    return False


def anthropic_configured() -> bool:
    return False


def stakeholder_llm_available(user_providers: Optional[Dict[str, Any]] = None) -> bool:
    """True when stakeholder simulation can call a real LLM."""
    if ollama_reachable():
        return True
    if user_providers:
        for info in user_providers.values():
            if isinstance(info, dict) and info.get("api_key"):
                return True
    return False


def choice_id(backend: str, model: str) -> str:
    return f"{backend.lower()}:{model}"


def parse_choice_id(choice_id: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    if not choice_id or ":" not in choice_id:
        return None, None
    backend, model = choice_id.split(":", 1)
    return backend.lower().strip(), model.strip()


def default_choice_id() -> str:
    model = (os.getenv("LLM_MODEL") or "").strip()

    tags = fetch_ollama_tags()
    if tags:
        tag = _pick_ollama_tag(tags, base_hint=model or None)
        return choice_id("ollama", tag.split(":")[0])
    pick = model or OLLAMA_FALLBACK_MODELS[0]
    return choice_id("ollama", pick)


def list_llm_choices(user_provider: str = "") -> List[Dict[str, Any]]:
    """Options for the chat model dropdown.
    user_provider can be "openai" or "anthropic" for user-stored API keys.
    """
    choices: List[Dict[str, Any]] = []
    seen: set[str] = set()

    def add(backend: str, model: str, label: str, provider: str, available: bool) -> None:
        cid = choice_id(backend, model)
        if cid in seen:
            return
        seen.add(cid)
        choices.append(
            {
                "id": cid,
                "backend": backend,
                "model": model,
                "label": label,
                "provider": provider,
                "available": available,
            }
        )

    if user_provider == "openai":
        for model in OPENAI_DEFAULT_MODELS:
            add("openai", model, f"OpenAI · {model}", "openai", True)

    if user_provider == "anthropic":
        for model in ["claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022", "claude-3-opus-20240229"]:
            add("anthropic", model, f"Anthropic · {model}", "anthropic", True)

    if user_provider == "gemini":
        for model in ["gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-2.5-flash-preview-04-17"]:
            add("gemini", model, f"Gemini · {model}", "gemini", True)

    if user_provider == "groq":
        for model in ["llama3-70b-8192", "llama3-8b-8192", "mixtral-8x7b-32768", "gemma2-9b-it"]:
            add("groq", model, f"Groq · {model}", "groq", True)

    if user_provider == "openrouter":
        for model in ["mistralai/mistral-7b-instruct", "openai/gpt-4o-mini", "anthropic/claude-3-5-sonnet"]:
            add("openrouter", model, f"OpenRouter · {model}", "openrouter", True)

    installed_ollama = fetch_ollama_model_names()
    ollama_models = list(
        dict.fromkeys(
            installed_ollama + OLLAMA_FALLBACK_MODELS
        )
    )
    if ollama_models:
        for model in ollama_models:
            available = model in installed_ollama
            add(
                "ollama",
                model,
                f"Ollama · {model}" + ("" if available else " (not installed)"),
                "ollama",
                available,
            )

    return choices


def selectable_choices() -> List[Dict[str, Any]]:
    """Choices worth showing in the UI (more than template-only)."""
    all_choices = list_llm_choices()
    non_template = [c for c in all_choices if c["provider"] != "template"]
    if not non_template:
        return all_choices
    return [c for c in all_choices if c["provider"] == "template" or c.get("available")]


def validate_choice_id(choice_id: Optional[str], user_provider: str = "") -> Optional[str]:
    if not choice_id:
        return default_choice_id()
    choices = list_llm_choices(user_provider=user_provider)
    by_id = {c["id"]: c for c in choices}
    if choice_id in by_id and by_id[choice_id].get("available", True):
        return choice_id
    return default_choice_id()


def get_llm_wrapper(rag: Any, backend: str, model: str) -> LLMWrapper:
    model_key = model or "builtin"
    cache_key = (id(rag), backend.lower(), model_key)
    if cache_key not in _wrapper_cache:
        wrapper_model = None if model_key in ("builtin", "template") else model_key
        _wrapper_cache[cache_key] = LLMWrapper(rag, backend=backend, model=wrapper_model)
    return _wrapper_cache[cache_key]


def resolve_llm_wrapper(rag: Any, choice_id: Optional[str], user_provider: str = "") -> LLMWrapper:
    resolved = validate_choice_id(choice_id, user_provider=user_provider)
    backend, model = parse_choice_id(resolved)
    if not backend or backend == "template":
        backend = "ollama"
        model = model if model and model not in ("builtin", "template") else None
    return get_llm_wrapper(rag, backend, model or "llama3.2")


def choice_label(choice_id: str, user_provider: str = "") -> str:
    for item in list_llm_choices(user_provider=user_provider):
        if item["id"] == choice_id:
            return str(item["label"])
    backend, model = parse_choice_id(choice_id)
    return f"{backend or 'llm'} · {model or 'default'}"
