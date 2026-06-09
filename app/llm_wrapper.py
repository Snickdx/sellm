"""
LLM wrapper for stakeholder simulation (RAG and direct-model modes).
Requires a configured LLM backend — no template fallback for stakeholder chat.
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional, Tuple

from app.scenario.direct_model import build_direct_user_message
from app.scenario.scenario_pack import ScenarioPack
from app.scenario.stakeholder_prompt import (
    STAKEHOLDER_LLM_REQUIRED_MSG,
    STAKEHOLDER_SYSTEM_PROMPT,
    build_stakeholder_user_message,
    format_retrieved_context,
)


class LLMWrapper:
    """RAG-backed stakeholder simulator using a real LLM backend."""

    def __init__(self, rag, backend: str = "ollama", model: str = None):
        self.rag = rag
        self.backend = backend.lower()
        self.model = model or self._get_default_model()
        self.temperature = self._get_env_float("OPENAI_TEMPERATURE", 0.4)
        self.max_tokens = self._get_env_int("OPENAI_MAX_TOKENS", 280)
        self.rag_top_k = self._get_env_int("RAG_TOP_K", 5)
        self.ollama_top_p = self._get_env_float("OLLAMA_TOP_P", 0.9)

        if self.backend == "ollama":
            self._init_ollama()
        elif self.backend == "openai":
            self._init_openai()
        elif self.backend == "anthropic":
            self._init_anthropic()
        elif self.backend == "template":
            print("⚠ Template backend cannot run stakeholder simulation")
        else:
            print(f"Unknown backend {self.backend}")
            self.backend = "template"

    def _get_env_float(self, name: str, default: float) -> float:
        raw_value = os.getenv(name)
        if raw_value is None:
            return default
        try:
            return float(raw_value)
        except ValueError:
            return default

    def _get_env_int(self, name: str, default: int) -> int:
        raw_value = os.getenv(name)
        if raw_value is None:
            return default
        try:
            return int(raw_value)
        except ValueError:
            return default

    def _get_default_model(self) -> str:
        if self.backend == "ollama":
            return "llama3.2"
        if self.backend == "openai":
            return "gpt-4o-mini"
        if self.backend == "anthropic":
            return "claude-3-5-sonnet-20241022"
        return "builtin"

    def _ollama_host(self) -> str:
        return (os.getenv("OLLAMA_HOST") or "http://localhost:11434").rstrip("/")

    def _init_ollama(self):
        try:
            import requests
            from app.llm_registry import resolve_ollama_model

            self.requests = requests
            self.ollama_host = self._ollama_host()
            response = requests.get(f"{self.ollama_host}/api/tags", timeout=2)
            if response.status_code == 200:
                resolved = resolve_ollama_model(self.model)
                if resolved:
                    self.model = resolved
                print(f"✓ Ollama connected, using model: {self.model}")
            else:
                print("⚠ Ollama not responding")
        except Exception as e:
            print(f"⚠ Ollama not available ({e})")

    def _init_openai(self):
        try:
            import openai

            self.openai = openai
            print(f"✓ OpenAI client initialized, using model: {self.model}")
        except ImportError:
            print("⚠ openai package not installed")

    def _init_anthropic(self):
        try:
            import httpx

            self.httpx = httpx
            print(f"✓ Anthropic client initialized, using model: {self.model}")
        except ImportError:
            print("⚠ httpx not installed")

    def _can_use_backend(
        self,
        *,
        provider_override: Optional[str] = None,
        api_key_override: Optional[str] = None,
    ) -> bool:
        if api_key_override and provider_override:
            return True
        return self.backend in ("ollama", "openai", "anthropic")

    def _ollama_generate_payload(self, prompt: str, model: str, *, system: str = "") -> dict:
        full_prompt = f"{system}\n\n{prompt}" if system else prompt
        return {
            "model": model,
            "prompt": full_prompt,
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "top_p": self.ollama_top_p,
            },
        }

    def _generate_with_ollama(self, user_message: str, *, system: str) -> str:
        from app.llm_registry import resolve_ollama_model

        model = resolve_ollama_model(self.model) or self.model
        response = self.requests.post(
            f"{self.ollama_host}/api/generate",
            json=self._ollama_generate_payload(user_message, model, system=system),
            timeout=120,
        )
        if response.status_code == 200:
            self.model = model
            return response.json().get("response", "").strip()
        raise Exception(f"Ollama API error {response.status_code}: {(response.text or '')[:200]}")

    def _generate_with_openai(self, user_message: str, *, system: str) -> str:
        response = self.openai.ChatCompletion.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_message},
            ],
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        return response.choices[0].message.content.strip()

    def _generate_with_anthropic(self, user_message: str, *, system: str, api_key: str) -> str:
        if not api_key:
            raise ValueError("Anthropic API key is required")
        response = self.httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": self.model,
                "max_tokens": max(self.max_tokens, 400),
                "temperature": min(1.0, self.temperature),
                "system": system,
                "messages": [{"role": "user", "content": user_message}],
            },
            timeout=120,
        )
        response.raise_for_status()
        data = response.json()
        parts = data.get("content") or []
        text = "".join(p.get("text", "") for p in parts if p.get("type") == "text")
        return text.strip()

    def _call_openai_compatible(
        self,
        user_message: str,
        *,
        system: str,
        api_key: str,
        base_url: str,
        model: str,
    ) -> str:
        import requests as req

        url = f"{base_url.rstrip('/')}/chat/completions"
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_message},
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        resp = req.post(
            url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=120,
        )
        if resp.status_code != 200:
            raise Exception(f"OpenAI-compatible API error {resp.status_code}: {resp.text}")
        data = resp.json()
        choice = data.get("choices", [{}])[0]
        return choice.get("message", {}).get("content", "").strip()

    def _generate_stakeholder(
        self,
        user_message: str,
        *,
        provider_override: Optional[str] = None,
        api_key_override: Optional[str] = None,
        base_url_override: Optional[str] = None,
    ) -> str:
        system = STAKEHOLDER_SYSTEM_PROMPT

        if not self._can_use_backend(
            provider_override=provider_override,
            api_key_override=api_key_override,
        ):
            raise RuntimeError(STAKEHOLDER_LLM_REQUIRED_MSG)

        if api_key_override and provider_override:
            provider_lower = provider_override.lower()
            base_url = base_url_override or {
                "openai": "https://api.openai.com/v1",
                "groq": "https://api.groq.com/openai/v1",
                "openrouter": "https://openrouter.ai/api/v1",
            }.get(provider_lower, "https://api.openai.com/v1")
            model_map = {
                "openai": "gpt-3.5-turbo",
                "groq": "llama3-70b-8192",
                "openrouter": "mistralai/mistral-7b-instruct",
            }
            model = model_map.get(provider_lower, "gpt-3.5-turbo")
            return self._call_openai_compatible(
                user_message,
                system=system,
                api_key=api_key_override,
                base_url=base_url,
                model=model,
            )

        if self.backend == "ollama":
            return self._generate_with_ollama(user_message, system=system)
        if self.backend == "openai":
            return self._generate_with_openai(user_message, system=system)
        if self.backend == "anthropic":
            return self._generate_with_anthropic(
                user_message,
                system=system,
                api_key=api_key_override or "",
            )

        raise RuntimeError(STAKEHOLDER_LLM_REQUIRED_MSG)

    def _finish_response(self, text: str) -> str:
        text = (text or "").strip()
        if text and not text.endswith((".", "?", "!")):
            text += "."
        return text

    def generate_stakeholder_from_results(
        self,
        query: str,
        context_results: List[Dict],
        conversation_history: Optional[List[Dict]] = None,
        *,
        provider_override: Optional[str] = None,
        api_key_override: Optional[str] = None,
        base_url_override: Optional[str] = None,
        scenario_pack: Optional[ScenarioPack] = None,
    ) -> str:
        context_block = format_retrieved_context(
            context_results, max_items=self.rag_top_k
        )
        if scenario_pack:
            context_block = (
                f"{scenario_pack.as_prompt_block()}\n\n"
                f"Retrieved highlights for this question:\n{context_block}"
            )
        user_message = build_stakeholder_user_message(
            query,
            context_block=context_block,
            conversation_history=conversation_history,
            context_label="Supporting project context",
        )
        response = self._generate_stakeholder(
            user_message,
            provider_override=provider_override,
            api_key_override=api_key_override,
            base_url_override=base_url_override,
        )
        return self._finish_response(response)

    def generate_stakeholder_direct(
        self,
        query: str,
        scenario_pack: ScenarioPack,
        conversation_history: Optional[List[Dict]] = None,
        *,
        provider_override: Optional[str] = None,
        api_key_override: Optional[str] = None,
        base_url_override: Optional[str] = None,
    ) -> str:
        user_message = build_direct_user_message(
            query, scenario_pack, conversation_history
        )
        response = self._generate_stakeholder(
            user_message,
            provider_override=provider_override,
            api_key_override=api_key_override,
            base_url_override=base_url_override,
        )
        return self._finish_response(response)

    def generate_response_from_results(
        self,
        query: str,
        context_results: List[Dict],
        conversation_history: Optional[List[Dict]] = None,
        behavior_system_suffix: Optional[str] = None,
        force_coach: bool = False,
        provider_override: Optional[str] = None,
        api_key_override: Optional[str] = None,
        base_url_override: Optional[str] = None,
        scenario_pack: Optional[ScenarioPack] = None,
    ) -> Tuple[str, Optional[str]]:
        del behavior_system_suffix, force_coach
        text = self.generate_stakeholder_from_results(
            query,
            context_results or [],
            conversation_history,
            provider_override=provider_override,
            api_key_override=api_key_override,
            base_url_override=base_url_override,
            scenario_pack=scenario_pack,
        )
        return text, None

    def generate_response(
        self,
        query: str,
        conversation_history: Optional[List[Dict]] = None,
        behavior_system_suffix: Optional[str] = None,
        force_coach: bool = False,
        provider_override: Optional[str] = None,
        api_key_override: Optional[str] = None,
        base_url_override: Optional[str] = None,
        scenario_pack: Optional[ScenarioPack] = None,
    ) -> Tuple[str, Optional[str]]:
        del behavior_system_suffix, force_coach
        if not self.rag:
            raise RuntimeError("RAG engine required for retrieval modes")
        results = self.rag.search(query, n_results=self.rag_top_k, filter_by_sheet_type=True)
        return self.generate_response_from_results(
            query,
            results,
            conversation_history=conversation_history,
            provider_override=provider_override,
            api_key_override=api_key_override,
            base_url_override=base_url_override,
            scenario_pack=scenario_pack,
        )

    def generate_raw(self, system: str, user: str) -> str:
        """One-shot LLM call for meta tasks (reflection). Not used for stakeholder chat."""
        system = (system or "").strip()
        user = (user or "").strip()
        temp = min(0.5, self.temperature)

        if self.backend == "ollama":
            try:
                return self._generate_with_ollama(user, system=system or "You are a precise assistant.")
            except Exception as e:
                print(f"Error generating reflection (Ollama): {e}")
                raise

        if self.backend == "openai":
            return self._generate_with_openai(user, system=system or "You are a precise assistant.")

        if self.backend == "anthropic":
            return self._generate_with_anthropic(
                user,
                system=system or "You are a precise assistant.",
                api_key="",
            )

        return (
            '{"performance_notes":"No LLM backend for reflection.",'
            '"patch":{"global":{},"query_overrides_add":[],"pattern_overrides_add":[]}}'
        )
