"""
LLM wrapper for generating human-like stakeholder responses
Supports multiple backends: Ollama (recommended), OpenAI, or template fallback
"""
import os
from typing import List, Dict, Optional, Tuple
import random

from app.coach import format_coach_context, is_coach_query
from app.stakeholder_tone import STAKEHOLDER_PROMPT_RULES, apply_plain_language

class LLMWrapper:
    """Wrapper for different LLM backends with RAG context"""
    
    def __init__(self, rag, backend: str = "ollama", model: str = None):
        """
        Initialize LLM wrapper
        
        Args:
            rag: RequirementsRAG instance
            backend: "ollama", "openai", "anthropic", or "template" (fallback)
            model: Model name (e.g., "llama3.2", "gpt-4o-mini", "claude-3-5-sonnet-20241022")
        """
        self.rag = rag
        self.backend = backend.lower()
        self.model = model or self._get_default_model()
        self.temperature = self._get_env_float("OPENAI_TEMPERATURE", 0.4)
        self.max_tokens = self._get_env_int("OPENAI_MAX_TOKENS", 280)
        self.rag_top_k = self._get_env_int("RAG_TOP_K", 5)
        self.ollama_top_p = self._get_env_float("OLLAMA_TOP_P", 0.9)
        
        # Initialize backend
        if self.backend == "ollama":
            self._init_ollama()
        elif self.backend == "openai":
            self._init_openai()
        elif self.backend == "anthropic":
            self._init_anthropic()
        elif self.backend == "template":
            print("Using template-based fallback (limited quality)")
        else:
            print(f"Unknown backend {self.backend}, falling back to template")
            self.backend = "template"

    def _get_env_float(self, name: str, default: float) -> float:
        """Read float env var with safe fallback."""
        raw_value = os.getenv(name)
        if raw_value is None:
            return default
        try:
            return float(raw_value)
        except ValueError:
            print(f"Invalid {name}='{raw_value}', using default {default}")
            return default

    def _get_env_int(self, name: str, default: int) -> int:
        """Read int env var with safe fallback."""
        raw_value = os.getenv(name)
        if raw_value is None:
            return default
        try:
            return int(raw_value)
        except ValueError:
            print(f"Invalid {name}='{raw_value}', using default {default}")
            return default
    
    def _get_default_model(self) -> str:
        """Get default model for each backend"""
        if self.backend == "ollama":
            return "llama3.2"  # or "mistral", "phi3", etc.
        elif self.backend == "openai":
            return "gpt-4o-mini"
        elif self.backend == "anthropic":
            return "claude-3-5-sonnet-20241022"
        return "template"

    def _ollama_host(self) -> str:
        return (os.getenv("OLLAMA_HOST") or "http://localhost:11434").rstrip("/")
    
    def _init_ollama(self):
        """Initialize Ollama client"""
        try:
            import requests
            from app.llm_registry import resolve_ollama_model

            self.requests = requests
            self.ollama_host = self._ollama_host()
            response = requests.get(f"{self.ollama_host}/api/tags", timeout=2)
            if response.status_code == 200:
                resolved = resolve_ollama_model(self.model)
                if resolved:
                    if resolved != self.model:
                        print(
                            f"✓ Ollama connected; resolved model {self.model!r} -> {resolved!r}"
                        )
                    self.model = resolved
                print(f"✓ Ollama connected, using model: {self.model}")
            else:
                print("⚠ Ollama not responding, falling back to template")
                self.backend = "template"
        except Exception as e:
            print(f"⚠ Ollama not available ({e}), falling back to template")
            self.backend = "template"
    
    def _init_openai(self):
        """Initialize OpenAI client"""
        try:
            import openai
            self.openai = openai
            print(f"✓ OpenAI client initialized, using model: {self.model}")
        except ImportError:
            print("⚠ openai package not installed, falling back to template")
            self.backend = "template"

    def _init_anthropic(self):
        """Initialize Anthropic (Messages API via httpx)."""
        try:
            import httpx
            self.httpx = httpx
            print(f"✓ Anthropic client initialized, using model: {self.model}")
        except ImportError:
            print("⚠ httpx not installed, falling back to template")
            self.backend = "template"
    
    def _build_rag_prompt(
        self,
        query: str,
        context_results: List[Dict],
        conversation_history: Optional[List[Dict]] = None,
        behavior_suffix: str = "",
    ) -> str:
        """Build a prompt with RAG context for the LLM"""
        # Extract relevant information from context
        context_text = []
        for result in context_results[: self.rag_top_k]:
            doc = result.get('document', '')
            # Extract key information (skip "Sheet: X" line)
            lines = doc.split('\n')[1:]
            info_parts = []
            for line in lines:
                if ':' in line:
                    key, value = line.split(':', 1)
                    key = key.strip()
                    value = value.strip()
                    if value and value.lower() not in ['nan', 'none', '']:
                        # Only include important fields
                        if key.lower() in ['id', 'name', 'title', 'description', 'role', 
                                         'type', 'stakeholder', 'client', 'goal', 'feature', 
                                         'requirement', 'risk', 'cost', 'budget']:
                            info_parts.append(f"{key}: {value}")
            
            if info_parts:
                context_text.append(" | ".join(info_parts))
        
        context_str = "\n".join(context_text) if context_text else "No specific information found."

        history_text = ""
        if conversation_history:
            recent_turns = conversation_history[-6:]
            lines = []
            for turn in recent_turns:
                role = turn.get("role", "user")
                content = turn.get("content", "")
                if content:
                    lines.append(f"{role}: {content}")
            if lines:
                history_text = "\n".join(lines)
            else:
                history_text = "No prior conversation."
        else:
            history_text = "No prior conversation."

        suffix_block = ""
        if (behavior_suffix or "").strip():
            suffix_block = (
                "\n\nAdditional behavior instructions from training config (follow these in addition to the above):\n"
                f"{behavior_suffix.strip()}\n"
            )

        # Build the prompt
        prompt = f"""You are a non-technical stakeholder in a software project. You're being interviewed by someone gathering requirements. 
You speak casually and informally - like a real person, not a formal document. You don't use technical jargon.

{STAKEHOLDER_PROMPT_RULES}

Below is the project information available about this specific project. Use it as the ground truth for project-specific facts (goals, features, stakeholders, budget, etc.). You can also draw on your general knowledge to explain basic concepts, define terms, or give context — real stakeholders know things beyond just what's written down.

Project information:
{context_str}

Recent conversation:
{history_text}

Question: {query}

Instructions:
- Stay in character as the stakeholder only — never mention the interview, the interviewer, or that you are being asked questions
- Answer the user's direct question first, in the first sentence
- Be specific using the project information; do not say you are unsure when the notes already name people, goals, or user types
- User types in this project include Admin, HR, Employee, and external parties (e.g. Courts, Tax, NI, Employer) — Employees are people paid through the system, not a "department"
- Do not cite internal goal codes like "Goal G3"; describe goals in plain business language
- Use casual language: "Oh, well...", "Let me think...", "Yeah, there are..."
- Don't mention sheets, documents, or technical sources
- For processes (sign-up, onboarding, approvals): only describe steps that appear in the project information; otherwise say you are not sure of every step rather than inventing emails, portals, or training
- Avoid repeating the same list of departments or user types you already gave earlier in the conversation unless the question needs more detail
- If asked about worries, risks, or concerns, answer with your top concerns (cost, compliance, deadlines, etc.) — do not recite the project background or company introduction
- Keep it natural and human-like; use proper grammar but stay informal
- End with a short casual line — vary it (e.g. "What else do you want to know?", "Happy to go deeper on any of that.") — do not use "Does that help?" every time
{suffix_block}
Your response:"""
        
        return prompt

    def _build_coach_prompt(
        self,
        query: str,
        context_results: List[Dict],
        conversation_history: Optional[List[Dict]] = None,
    ) -> str:
        """Prompt for interviewer domain coaching (not stakeholder role-play)."""
        context_str = format_coach_context(context_results, max_items=self.rag_top_k)

        history_text = ""
        if conversation_history:
            recent_turns = conversation_history[-4:]
            lines = []
            for turn in recent_turns:
                role = turn.get("role", "user")
                content = turn.get("content", "")
                if content:
                    lines.append(f"{role}: {content}")
            if lines:
                history_text = "\n".join(lines)

        history_block = (
            f"\nRecent conversation:\n{history_text}\n" if history_text else ""
        )

        return f"""You are a domain coach helping someone prepare to interview stakeholders on a software project.

The user is learning the domain — they are NOT practicing the interview right now. Use ONLY the project knowledge below.

Project knowledge (from requirements workbook):
{context_str}
{history_block}
Question: {query}

Instructions:
- Start with a clear, plain-language definition or explanation (2–4 sentences).
- Explain how this concept shows up in THIS project using facts from the knowledge above.
- Add a short bullet list (3–5 items) of what a good interviewer should clarify with a real stakeholder.
- Write as a helpful coach, not as the stakeholder. Do NOT use openings like "So, it's about..." or "Oh, well...".
- Do not invent facts not supported by the knowledge; say what is unclear if needed.
- Stay concise (under ~200 words unless the topic needs more).
- CRITICAL: Never quote or directly reference the requirements documentation. Explain concepts in your own words as a teaching coach, as if you naturally understand the domain. Do not say "according to the requirements" or "the documentation states" or anything similar.

Your answer:"""

    def _generate_coach_with_openai(self, prompt: str) -> str:
        system_content = (
            "You are a domain coach for requirements-interview training. "
            "Explain concepts clearly to interviewers using only the project facts provided. "
            "Never role-play as the stakeholder. "
            "Never quote or directly reference the requirements documentation — explain in your own words as a teacher."
        )
        response = self.openai.ChatCompletion.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_content},
                {"role": "user", "content": prompt},
            ],
            temperature=min(0.5, self.temperature),
            max_tokens=max(self.max_tokens, 400),
        )
        return response.choices[0].message.content.strip()

    def _generate_coach_with_anthropic(self, prompt: str) -> str:
        return self._generate_with_anthropic(
            prompt,
            system=(
                "You are a domain coach for requirements-interview training. "
                "Explain concepts clearly to interviewers using only the project facts provided. "
                "Never role-play as the stakeholder. "
                "Never quote or directly reference the requirements documentation — explain in your own words as a teacher."
            ),
        )

    def _generate_coach_with_template(self, query: str, context_results: List[Dict]) -> str:
        """Structured coach fallback when no LLM API is available."""
        context_str = format_coach_context(context_results, max_items=5)
        if not context_str or context_str == "No matching project knowledge found.":
            return (
                "I don't have enough about that in the project knowledge base. "
                "Try rephrasing or ask the stakeholder directly in practice mode."
            )

        term = query.strip().rstrip("?.!")
        lines = [f"**Domain note** (from project materials)\n"]
        lines.append(
            f"Here is what the workbook says that relates to *{term}* — use this to shape interview questions, "
            "not as a final definition:\n"
        )
        for block in context_str.split("\n---\n")[:4]:
            snippet = " ".join(block.split())
            if len(snippet) > 320:
                snippet = snippet[:317] + "..."
            lines.append(f"- {snippet}")
        lines.append(
            "\n**As an interviewer**, ask the stakeholder: what it means in their words, who it affects, "
            "rules/exceptions, and any constraints or audit needs."
        )
        return "\n".join(lines)

    def _generate_with_anthropic(self, prompt: str, *, system: str) -> str:
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
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
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=120,
        )
        response.raise_for_status()
        data = response.json()
        parts = data.get("content") or []
        text = "".join(p.get("text", "") for p in parts if p.get("type") == "text")
        return text.strip()

    def _ollama_generate_payload(self, prompt: str, model: str) -> dict:
        return {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "top_p": self.ollama_top_p,
            },
        }

    def _generate_with_ollama(self, prompt: str) -> str:
        """Generate response using Ollama"""
        try:
            from app.llm_registry import resolve_ollama_model

            model = resolve_ollama_model(self.model) or self.model
            response = self.requests.post(
                f"{self.ollama_host}/api/generate",
                json=self._ollama_generate_payload(prompt, model),
                timeout=120,
            )

            if response.status_code == 404:
                resolved = resolve_ollama_model(self.model)
                if resolved and resolved != model:
                    self.model = resolved
                    response = self.requests.post(
                        f"{self.ollama_host}/api/generate",
                        json=self._ollama_generate_payload(prompt, resolved),
                        timeout=120,
                    )
                    model = resolved

            if response.status_code == 200:
                self.model = model
                return response.json().get("response", "").strip()

            detail = (response.text or "").strip()[:200]
            base = (model or "model").split(":")[0]
            raise Exception(
                f"Ollama API error {response.status_code} for model '{model}'. "
                f"{detail} "
                f"Install with: ollama pull {base}"
            )
        except Exception as e:
            print(f"Error calling Ollama: {e}")
            raise
    
    def _stakeholder_system_content(self, behavior_suffix: str = "") -> str:
        system_content = (
            "You are a non-technical stakeholder. Respond informally and naturally, like you're speaking in person.\n\n"
            f"{STAKEHOLDER_PROMPT_RULES}"
        )
        if (behavior_suffix or "").strip():
            system_content = (
                f"{system_content}\n\n"
                "Additional behavior instructions from training config:\n"
                f"{behavior_suffix.strip()}"
            )
        return system_content

    def _generate_with_openai(self, prompt: str, behavior_suffix: str = "") -> str:
        """Generate response using OpenAI"""
        try:
            system_content = self._stakeholder_system_content(behavior_suffix)
            response = self.openai.ChatCompletion.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": system_content,
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens
            )
            
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"Error calling OpenAI: {e}")
            raise

    def generate_raw(self, system: str, user: str) -> str:
        """
        One-shot LLM call for meta tasks (no RAG). Used for session reflection / tweak proposals.
        Does not pass output token caps so the provider/model sets the completion limit.
        """
        system = (system or "").strip()
        user = (user or "").strip()
        temp = min(0.5, self.temperature)

        if self.backend == "ollama":
            prompt = f"{system}\n\n---\n\n{user}" if system else user
            try:
                host = getattr(self, "ollama_host", self._ollama_host())
                response = self.requests.post(
                    f"{host}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "temperature": temp,
                            "top_p": self.ollama_top_p,
                        },
                    },
                    timeout=120,
                )
                if response.status_code == 200:
                    return response.json().get("response", "").strip()
                raise Exception(f"Ollama API error: {response.status_code}")
            except Exception as e:
                print(f"Error generating reflection (Ollama): {e}")
                raise

        if self.backend == "anthropic":
            try:
                return self._generate_with_anthropic(
                    user,
                    system=system or "You are a precise assistant.",
                )
            except Exception as e:
                print(f"Error generating reflection (Anthropic): {e}")
                raise

        if self.backend == "openai":
            try:
                response = self.openai.ChatCompletion.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system or "You are a precise assistant."},
                        {"role": "user", "content": user},
                    ],
                    temperature=temp,
                )
                return response.choices[0].message.content.strip()
            except Exception as e:
                print(f"Error generating reflection (OpenAI): {e}")
                raise

        return (
            '{"performance_notes":"Template backend cannot run reflection. Use ollama or openai.",'
            '"patch":{"global":{},"query_overrides_add":[],"pattern_overrides_add":[]}}'
        )
    
    def _generate_with_template(self, query: str, context_results: List[Dict]) -> str:
        """Fallback template-based generation (original SimpleLLM logic)"""
        # Import here to avoid circular imports
        try:
            from app.rag_backend import SimpleLLM
            simple_llm = SimpleLLM(self.rag)
            return apply_plain_language(simple_llm.generate_response(query))
        except ImportError:
            # Ultimate fallback
            return "I'm not sure how to answer that. Can you rephrase your question?"

    def _call_openai_compatible(
        self,
        prompt: str,
        api_key: str,
        base_url: str,
        model: str,
        behavior_suffix: str = "",
    ) -> str:
        """Call an OpenAI-compatible chat completions API using requests directly."""
        import requests as req
        url = f"{base_url.rstrip('/')}/chat/completions"
        system_content = (
            "You are a non-technical stakeholder. Respond informally and naturally, like you're speaking in person."
        )
        if (behavior_suffix or "").strip():
            system_content = (
                f"{system_content}\n\n"
                "Additional behavior instructions from training config:\n"
                f"{behavior_suffix.strip()}"
            )
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_content},
                {"role": "user", "content": prompt},
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
            timeout=60,
        )
        if resp.status_code != 200:
            raise Exception(f"OpenAI-compatible API error {resp.status_code}: {resp.text}")
        data = resp.json()
        choice = data.get("choices", [{}])[0]
        return choice.get("message", {}).get("content", "").strip()

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
    ) -> Tuple[str, Optional[str]]:
        """Generate response from precomputed retrieval results.

        Returns (text, style) where style is ``coach`` for domain-coach answers, else None.
        """
        use_coach = is_coach_query(query, force=force_coach)
        suffix = "" if use_coach else (behavior_system_suffix or "").strip()
        if not context_results:
            if use_coach:
                return (
                    "I couldn't find that topic in the project knowledge base. "
                    "Try a different term or switch to stakeholder practice mode and ask directly.",
                    "coach",
                )
            no_context_responses = [
                "Hmm, I'm not sure about that. Can you ask me something else?",
                "I don't really know much about that. What else would you like to know?",
                "That's not something I'm familiar with. Maybe try asking about something else?",
            ]
            return random.choice(no_context_responses), None

        if use_coach:
            prompt = self._build_coach_prompt(
                query, context_results, conversation_history=conversation_history
            )
            try:
                if self.backend == "ollama":
                    response = self._generate_with_ollama(prompt)
                elif self.backend == "openai":
                    response = self._generate_coach_with_openai(prompt)
                elif self.backend == "anthropic":
                    response = self._generate_coach_with_anthropic(prompt)
                else:
                    response = self._generate_coach_with_template(query, context_results)
            except Exception as e:
                print(f"Error generating coach response with {self.backend}: {e}")
                response = self._generate_coach_with_template(query, context_results)
            response = response.strip()
            if not response.endswith(("?", "!", ".")):
                response += "."
            return response, "coach"

        prompt = self._build_rag_prompt(
            query, context_results, conversation_history=conversation_history, behavior_suffix=suffix
        )

        # If user has provided their own API key, use that instead of the system default
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
            try:
                response = self._call_openai_compatible(prompt, api_key_override, base_url, model, behavior_suffix=suffix)
                response = response.strip()
                if not response.endswith(('?', '!', '.')):
                    response += "."
                return apply_plain_language(response), None
            except Exception as e:
                print(f"Error with user-provided API ({provider_override}): {e}")
                print("Falling back to system default backend")

        try:
            if self.backend == "ollama":
                response = self._generate_with_ollama(prompt)
            elif self.backend == "openai":
                response = self._generate_with_openai(prompt, behavior_suffix=suffix)
            elif self.backend == "anthropic":
                response = self._generate_with_anthropic(
                    prompt,
                    system=self._stakeholder_system_content(suffix),
                )
            else:
                response = self._generate_with_template(query, context_results)

            response = apply_plain_language(response.strip())
            if not response.endswith(('?', '!', '.')):
                response += "."
            return response, None
        except Exception as e:
            print(f"Error generating response with {self.backend}: {e}")
            if self.backend != "template":
                print("Falling back to template-based generation")
                tpl = self._generate_with_template(query, context_results)
                return apply_plain_language(tpl), None
            raise
    
    def generate_response(
        self,
        query: str,
        conversation_history: Optional[List[Dict]] = None,
        behavior_system_suffix: Optional[str] = None,
        force_coach: bool = False,
        provider_override: Optional[str] = None,
        api_key_override: Optional[str] = None,
        base_url_override: Optional[str] = None,
    ) -> Tuple[str, Optional[str]]:
        """Generate human-like response using RAG + LLM"""
        results = self.rag.search(query, n_results=self.rag_top_k, filter_by_sheet_type=True)
        return self.generate_response_from_results(
            query,
            results,
            conversation_history=conversation_history,
            behavior_system_suffix=behavior_system_suffix,
            force_coach=force_coach,
            provider_override=provider_override,
            api_key_override=api_key_override,
            base_url_override=base_url_override,
        )
