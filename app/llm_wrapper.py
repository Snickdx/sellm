"""
LLM wrapper for generating human-like stakeholder responses
Supports multiple backends: Ollama (recommended), OpenAI, or template fallback
"""
import os
from typing import List, Dict, Optional
import random

class LLMWrapper:
    """Wrapper for different LLM backends with RAG context"""
    
    def __init__(self, rag, backend: str = "ollama", model: str = None):
        """
        Initialize LLM wrapper
        
        Args:
            rag: RequirementsRAG instance
            backend: "ollama", "openai", or "template" (fallback)
            model: Model name (e.g., "llama3.2", "gpt-3.5-turbo")
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
            return "gpt-3.5-turbo"
        return "template"
    
    def _init_ollama(self):
        """Initialize Ollama client"""
        try:
            import requests
            self.requests = requests
            # Test connection
            response = requests.get("http://localhost:11434/api/tags", timeout=2)
            if response.status_code == 200:
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
            if not os.getenv("OPENAI_API_KEY"):
                print("⚠ OPENAI_API_KEY not set, falling back to template")
                self.backend = "template"
            else:
                print(f"✓ OpenAI initialized, using model: {self.model}")
        except ImportError:
            print("⚠ openai package not installed, falling back to template")
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

Below is the project information available about this specific project. Use it as the ground truth for project-specific facts (goals, features, stakeholders, budget, etc.). You can also draw on your general knowledge to explain basic concepts, define terms, or give context — real stakeholders know things beyond just what's written down.

Project information:
{context_str}

Recent conversation:
{history_text}

Question: {query}

Instructions:
- Answer the user's direct question first, in the first sentence
- Be specific and avoid generic restatements
- Use casual language: "Oh, well...", "Let me think...", "Yeah, there are..."
- Don't mention sheets, documents, or technical sources
- Use project info for specifics, but feel free to use general knowledge to explain or elaborate naturally
- If the project info doesn't cover something, say so casually or draw on what you know
- Keep it natural and human-like
- Use proper grammar but stay informal
- End with a casual follow-up question like "Does that help?" or "What else do you want to know?"
{suffix_block}
Your response:"""
        
        return prompt
    
    def _generate_with_ollama(self, prompt: str) -> str:
        """Generate response using Ollama"""
        try:
            response = self.requests.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": self.temperature,
                        "top_p": self.ollama_top_p,
                    }
                },
                timeout=30
            )
            
            if response.status_code == 200:
                return response.json().get("response", "").strip()
            else:
                raise Exception(f"Ollama API error: {response.status_code}")
        except Exception as e:
            print(f"Error calling Ollama: {e}")
            raise
    
    def _generate_with_openai(self, prompt: str, behavior_suffix: str = "") -> str:
        """Generate response using OpenAI"""
        try:
            system_content = (
                "You are a non-technical stakeholder. Respond informally and naturally, like you're speaking in person."
            )
            if (behavior_suffix or "").strip():
                system_content = (
                    f"{system_content}\n\n"
                    "Additional behavior instructions from training config:\n"
                    f"{behavior_suffix.strip()}"
                )
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
                response = self.requests.post(
                    "http://localhost:11434/api/generate",
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
            return simple_llm.generate_response(query)
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
        provider_override: Optional[str] = None,
        api_key_override: Optional[str] = None,
        base_url_override: Optional[str] = None,
    ) -> str:
        """Generate response from precomputed retrieval results."""
        suffix = (behavior_system_suffix or "").strip()
        if not context_results:
            no_context_responses = [
                "Hmm, I'm not sure about that. Can you ask me something else?",
                "I don't really know much about that. What else would you like to know?",
                "That's not something I'm familiar with. Maybe try asking about something else?",
            ]
            return random.choice(no_context_responses)

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
                return response
            except Exception as e:
                print(f"Error with user-provided API ({provider_override}): {e}")
                print("Falling back to system default backend")

        try:
            if self.backend == "ollama":
                response = self._generate_with_ollama(prompt)
            elif self.backend == "openai":
                response = self._generate_with_openai(prompt, behavior_suffix=suffix)
            else:
                response = self._generate_with_template(query, context_results)

            response = response.strip()
            if not response.endswith(('?', '!', '.')):
                response += "."
            return response
        except Exception as e:
            print(f"Error generating response with {self.backend}: {e}")
            if self.backend != "template":
                print("Falling back to template-based generation")
                return self._generate_with_template(query, context_results)
            raise
    
    def generate_response(
        self,
        query: str,
        conversation_history: Optional[List[Dict]] = None,
        behavior_system_suffix: Optional[str] = None,
        provider_override: Optional[str] = None,
        api_key_override: Optional[str] = None,
        base_url_override: Optional[str] = None,
    ) -> str:
        """Generate human-like response using RAG + LLM"""
        results = self.rag.search(query, n_results=self.rag_top_k, filter_by_sheet_type=True)
        return self.generate_response_from_results(
            query,
            results,
            conversation_history=conversation_history,
            behavior_system_suffix=behavior_system_suffix,
            provider_override=provider_override,
            api_key_override=api_key_override,
            base_url_override=base_url_override,
        )
