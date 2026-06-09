# Refactor notes — stakeholder simulator comparison modes

## What changed

- **Removed domain coach mode** entirely (`app/coach.py` deleted). The app no longer auto-switches to teaching/explainer responses.
- **Added Direct Model mode** — full scenario pack from `data.xlsx` is placed in the LLM prompt (no retrieval).
- **Compare All** now runs **Vector RAG**, **Neo4j RAG**, **Hybrid RAG**, and **Direct Model** on the same question.
- **Unified stakeholder prompt** in `app/scenario/stakeholder_prompt.py` for every mode.
- **Scenario pack builder** in `app/scenario/scenario_pack.py` compiles workbook sheets into structured context.
- **No template fallback** for stakeholder chat — a real LLM (Ollama or user-configured API key) is required.
- **Behavior tweaks** are no longer applied to normal stakeholder responses (feedback/reflection APIs may still exist when `TWEAK_MODE_ENABLED=true`).

## Chat modes

| UI label | `response_mode` | Behavior |
|----------|-----------------|----------|
| Vector RAG | `vector` | Chroma retrieval → stakeholder LLM |
| Neo4j RAG | `neo4j` | Graph retrieval → stakeholder LLM |
| Hybrid RAG | `hybrid` | Router picks chroma / neo4j / blend → stakeholder LLM |
| Direct Model | `direct` | Full scenario pack in prompt → stakeholder LLM |
| Compare All | `compare` | All four modes side by side |

## Request flow

```text
user message
→ auth + conversation
→ selected mode
→ retrieve (RAG) OR compile scenario pack (direct)
→ STAKEHOLDER_SYSTEM_PROMPT + context + history
→ LLM
→ save message + mode badge
```

## Instructor debug metadata

Send `"debug": true` in `POST /api/chat` to receive optional `debug` in the JSON response (retrieved chunk excerpts, hybrid routing). Hidden from trainees by default in the UI.

## How to compare approaches

1. Sign in and pick **Compare All**.
2. Ask the same question you would use in a real interview, e.g.:
   - Can you tell me about the project?
   - What are you most worried about?
   - Who else is involved?
3. Read the four sections and judge:
   - Does the answer address the question directly?
   - Does it sound like a person vs. a document dump?
   - Does retrieval add grounding or add noise?

## LLM requirement

If no Ollama model is running and no user API key is configured, chat returns:

```text
Stakeholder simulation requires a configured LLM backend. Please configure Ollama, OpenAI, Anthropic, Groq, or OpenRouter.
```

Configure via **⚙️ API Configuration** in the side nav or run Ollama locally with `LLM_BACKEND=ollama`.

## Key files

- `app/scenario/scenario_pack.py` — workbook → scenario pack
- `app/scenario/stakeholder_prompt.py` — shared persona rules
- `app/scenario/direct_model.py` — direct-mode message builder
- `app/llm_wrapper.py` — stakeholder generation (no coach/template)
- `app/api/app.py` — mode routing and compare orchestration
