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
    
    def _build_rag_prompt(self, query: str, context_results: List[Dict]) -> str:
        """Build a prompt with RAG context for the LLM"""
        # Extract relevant information from context
        context_text = []
        for result in context_results[:3]:  # Top 3 results
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
        
        # Build the prompt
        prompt = f"""You are a non-technical stakeholder in a software project. You're being interviewed by someone gathering requirements. 
You speak casually and informally - like a real person, not a formal document. You don't use technical jargon.

Based on the following information from the project, answer the question naturally and conversationally:

{context_str}

Question: {query}

Instructions:
- Answer as if you're speaking in person, not writing a document
- Use casual language: "Oh, well...", "Let me think...", "Yeah, there are..."
- Don't mention sheets, documents, or technical sources
- If you don't know something, say so casually
- Keep it natural and human-like
- Use proper grammar but stay informal
- End with a casual follow-up question like "Does that help?" or "What else do you want to know?"

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
                        "temperature": 0.7,  # More creative/conversational
                        "top_p": 0.9,
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
    
    def _generate_with_openai(self, prompt: str) -> str:
        """Generate response using OpenAI"""
        try:
            response = self.openai.ChatCompletion.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a non-technical stakeholder. Respond informally and naturally, like you're speaking in person."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.7,
                max_tokens=300
            )
            
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"Error calling OpenAI: {e}")
            raise
    
    def _generate_with_template(self, query: str, context_results: List[Dict]) -> str:
        """Fallback template-based generation (original SimpleLLM logic)"""
        # Import here to avoid circular imports
        try:
            from rag_backend import SimpleLLM
            simple_llm = SimpleLLM(self.rag)
            return simple_llm.generate_response(query)
        except ImportError:
            # Ultimate fallback
            return "I'm not sure how to answer that. Can you rephrase your question?"
    
    def generate_response(self, query: str) -> str:
        """Generate human-like response using RAG + LLM"""
        # Get relevant context
        results = self.rag.search(query, n_results=5, filter_by_sheet_type=True)
        
        if not results:
            # No context found
            no_context_responses = [
                "Hmm, I'm not sure about that. Can you ask me something else?",
                "I don't really know much about that. What else would you like to know?",
                "That's not something I'm familiar with. Maybe try asking about something else?",
            ]
            return random.choice(no_context_responses)
        
        # Build prompt with RAG context
        prompt = self._build_rag_prompt(query, results)
        
        # Generate response based on backend
        try:
            if self.backend == "ollama":
                response = self._generate_with_ollama(prompt)
            elif self.backend == "openai":
                response = self._generate_with_openai(prompt)
            else:
                # Template fallback
                response = self._generate_with_template(query, results)
            
            # Clean up response (remove any unwanted formatting)
            response = response.strip()
            
            # Ensure it ends with a question or casual phrase
            if not response.endswith(('?', '!', '.')):
                response += "."
            
            return response
            
        except Exception as e:
            print(f"Error generating response with {self.backend}: {e}")
            # Fallback to template
            if self.backend != "template":
                print("Falling back to template-based generation")
                return self._generate_with_template(query, results)
            raise
