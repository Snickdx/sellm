# Requirements Gathering Training System - RAG Implementation

A RAG-based training system that simulates a non-technical stakeholder for requirements gathering practice. The system uses an Excel-based knowledge source to role-play as a stakeholder, providing informal, human-like responses that trainees must extract, document, and formalize into proper requirements documentation.

## Purpose

This system is designed for **requirements gathering training**. It simulates a non-technical stakeholder who provides information in a casual, informal manner - just like in real-world requirements gathering sessions. 

**Training Objectives:**

- Practice asking effective questions to extract requirements
- Learn to identify key information from informal, unstructured conversations
- Develop skills in formalizing informal stakeholder input into structured requirements
- Practice identifying gaps and asking appropriate follow-up questions
- Experience the challenge of working with non-technical stakeholders

**Important**: The system does NOT reference the knowledge source directly. Responses are human-like and informal, as if speaking with a real non-technical stakeholder. Trainees must take notes during the conversation and then formalize the information into proper requirements documentation.

## Features

- **Stakeholder simulation**: Role-plays as a non-technical stakeholder with plain, informal language
- **Comparison modes**: Vector RAG, Neo4j RAG, Hybrid RAG, **Direct Model** (full scenario in prompt), and **Compare All**
- **Dual RAG**: ChromaDB (vector) and Neo4j (vector + graph), usable separately or via **hybrid** auto-routing
- **LLM backends**: Ollama (local) or per-user API keys (OpenAI, Anthropic, Groq, OpenRouter); stakeholder chat requires a real LLM
- **Scenario pack**: `data.xlsx` compiled into structured context for direct mode and optional RAG prompt enrichment
- **Auth + persistence**: Login, per-user conversations (SQLite/Postgres), reflection threads for meta-review
- **Responsive UI**: Collapsible side nav on mobile (conversations, new chat, API config)
- **Excel knowledge base**: `data.xlsx` is ground truth for retrieval (not cited in stakeholder answers)

## Installation

1. Install Python dependencies:

```bash
pip install -r requirements.txt
```

**Note**: The project includes a compatibility fix in `app/fix_pytree.py` for torch/transformers version compatibility issues. It is applied automatically when importing the RAG modules.

1. **Configure environment variables** (recommended):

```bash
# Copy the example env file (app/.env is loaded first by the app)
cp .env.example app/.env

# Edit app/.env with your settings
# On Windows: copy .env.example app\.env
```

The `.env` file allows you to configure:

- RAG backend (ChromaDB or Neo4j)
- Neo4j connection settings
- LLM backend (Ollama, OpenAI, or template)
- LLM model selection

See [`.env.example`](.env.example) for all options (local paths, Docker `/app` paths, Neo4j, MCP/hybrid).

**Important**: `app/.env` and `.env` are git-ignored. Copy from `.env.example` only — never commit secrets.

The app loads **`app/.env` first**, then project-root **`.env`** (later files do not override earlier keys).

## Deployment (Docker / EasyPanel)

Production deployment uses the repo-root **`Dockerfile`** (Chroma index is built into the image; empty volume mounts are re-seeded at startup). See **[docs/DEPLOY_EASYPANEL.md](docs/DEPLOY_EASYPANEL.md)** for EasyPanel steps (build, proxy port `8000`, PostgreSQL, volume on `/app/storage`, and environment variables).

Local smoke test:

```bash
docker compose up --build
```

Use `docker compose --profile postgres up --build` with `CONVERSATION_DB_URL=postgresql+psycopg2://sellm:sellm@postgres:5432/sellm` for a Postgres-backed stack.

**Hybrid mode** routes each question to Chroma (semantic) or Neo4j (graph/relationships), or blends both.

## Usage

1. Make sure your Excel file `data.xlsx` is in the project directory. This file contains the stakeholder knowledge base.
2. **Configure your environment** (optional but recommended):
  - Copy `.env.example` to `app/.env`
  - Edit `app/.env` (Neo4j password, LLM model, etc.)
  - The app will automatically load these settings
3. Start the server:

```bash
python -m app.main
```

Or using uvicorn directly:

```bash
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

1. Open your browser and navigate to:

```
http://localhost:8000
```

1. **Sign in** — default training users are seeded on startup (`nick`, `wayne`, `claudine`, `snick`; password `badPassword1`). Add more:

```bash
python -m setup.users.manage_users add myuser mypassword
python -m setup.users.manage_users list
```

1. Start practicing requirements gathering!
  - Ask questions as you would in a real stakeholder interview
  - Take notes during the conversation (outside the system)
  - After the session, formalize the informal responses into structured requirements documentation

### Environment Variables

You can configure the system using environment variables (via `.env` file or system environment):

**RAG Backend:**

- `RAG_BACKEND`: `"chromadb"` (default) or `"neo4j"`

**Neo4j** (for `RAG_BACKEND=neo4j`, **neo4j** chat mode, or hybrid fallback):

- `NEO4J_URI`: Neo4j connection URI (default: `bolt://localhost:7687`)
- `NEO4J_USER`: Neo4j username (default: `neo4j`)
- `NEO4J_PASSWORD`: Neo4j password (default: `password`)

Load graph data once: `python -m setup.neo4j.load_graph`

**Hybrid routing** (optional):

- `HYBRID_ROUTE_MARGIN`: Score gap to choose one backend vs blend (default: `0.15`)
- `HYBRID_TOP_K`: Retrieval depth for hybrid mode (default: `3`)

**LLM Backend:**

- `LLM_BACKEND`: `"ollama"` (default), `"openai"`, or `"template"`
- `LLM_MODEL`: Model name (e.g., `llama3.2`, `mistral`, `gpt-3.5-turbo`)

**OpenAI (if using OpenAI backend):**

- `OPENAI_API_KEY`: Your OpenAI API key

### Training Tips

- **Ask open-ended questions**: "Tell me about..." or "What are your concerns about..."
- **Follow up on vague answers**: If the stakeholder says "it should be fast", ask "What does 'fast' mean to you?"
- **Identify gaps**: Notice when information is missing and ask clarifying questions
- **Take comprehensive notes**: You'll need to formalize everything after the conversation
- **Practice different question types**: Try asking about stakeholders, goals, features, constraints, risks, and budget

## Architecture

### System overview

The app is a **FastAPI** service with a Jinja2 web UI. Each chat message goes through **auth → mode selection → retrieve or compile scenario pack → stakeholder prompt → LLM generation → persistence**. See **[docs/REFACTOR_NOTES.md](docs/REFACTOR_NOTES.md)** for the comparison-mode refactor.

```mermaid
flowchart TB
  subgraph client [Browser]
    UI[index.html + chat.js]
    Nav[Side nav: conversations / new chat / config]
  end

  subgraph api [FastAPI app/api/app.py]
    Auth[Bearer session auth]
    Chat[POST /api/chat]
    Store[(ConversationStore SQLite or Postgres)]
    Tweaks[behavior_tweaks.json]
  end

  subgraph retrieval [Retrieval layer]
    Vector[RequirementsRAG ChromaDB]
    Graph[RequirementsRAGNeo4j]
    Hybrid[HybridKnowledgeService + router]
  end

  subgraph generation [Generation layer]
    Scenario[scenario_pack + stakeholder_prompt]
    LLM[LLMWrapper + llm_registry]
  end

  KB[(data.xlsx)]

  UI --> Auth
  Nav --> UI
  Auth --> Chat
  Chat --> Store
  Chat --> Hybrid
  Chat --> Vector
  Chat --> Graph
  Hybrid --> Vector
  Hybrid --> Graph
  Vector --> KB
  Graph --> KB
  Chat --> Scenario
  Scenario --> LLM
  Vector --> LLM
  Graph --> LLM
  Chat --> Store
```

**At startup** (`app/api/app.py` lifespan):

1. Load `data.xlsx` into **Chroma** (`app/rag_backend.py`) and optionally **Neo4j** (`app/rag_backend_neo4j.py`).
2. Wire **HybridKnowledgeService** (`app/mcp/hybrid.py`) with both engines when available.
3. Initialize **LLMWrapper** via `llm_registry` (Ollama / OpenAI / Anthropic / template).
4. Seed default users and open the conversation database.

Hybrid routing uses `app/mcp/router.py` in-process (no separate MCP sidecar). Neo4j may be unavailable if credentials or the graph load fail; vector-only modes still work.

### Components

| Layer | Module(s) | Role |
|-------|-----------|------|
| **UI** | `app/web/templates/index.html`, `app/web/static/components/chat.js` | Chat, mode/LLM selectors, mobile side nav, settings modal, reflection UI |
| **API** | `app/api/app.py`, `app/api/schemas.py` | Routes, auth, chat orchestration, config |
| **Auth & history** | `app/storage/conversation_store.py` | Users, sessions, conversations, messages, reflection threads |
| **Vector RAG** | `app/rag_backend.py` | Embeddings, Chroma search, sheet-intent filtering, `SimpleLLM` template fallback |
| **Graph RAG** | `app/rag_backend_neo4j.py` | Neo4j vector + relationship traversal |
| **Hybrid** | `app/mcp/hybrid.py`, `app/mcp/router.py` | Per-question route: `chroma`, `neo4j`, or `blend` |
| **Scenario** | `app/scenario/scenario_pack.py`, `app/scenario/stakeholder_prompt.py`, `app/scenario/direct_model.py` | Workbook → scenario pack; shared stakeholder persona |
| **LLM** | `app/llm_wrapper.py`, `app/llm_registry.py` | Stakeholder generation (RAG + direct), model dropdown |
| **Tweaks** | `app/tweaks/behavior_tweaks.py`, `config/behavior/behavior_tweaks.json` | Optional reflection/feedback only (not applied to normal chat) |
| **Reflection** | `app/reflection.py` | Session meta-review and tweak draft proposals |
| **Knowledge** | `data.xlsx` | Source workbook (Goals, Features, Stakeholders, etc.) |

### How the chat works

End-to-end flow for `POST /api/chat`:

1. **Authenticate** — Browser sends `Authorization: Bearer <token>` (from `POST /api/auth/login`). Unauthenticated requests return 401.

2. **Conversation** — If `conversation_id` is omitted, a new conversation is created from the first message. Prior turns are loaded as `conversation_history` for the LLM (last few messages).

3. **Pick mode** — `response_mode` on the request (UI dropdown):
   - `vector` — Chroma retrieval → stakeholder LLM
   - `neo4j` — Neo4j retrieval → stakeholder LLM
   - `hybrid` — Auto-route to **chroma**, **neo4j**, or **blend**
   - `direct` — Full scenario pack in prompt (no retrieval) — baseline for comparison
   - `compare` — All four modes side by side in one message

4. **Context** — RAG modes retrieve top-k workbook chunks; direct mode uses the compiled scenario pack from `app/scenario/scenario_pack.py`. All modes share `app/scenario/stakeholder_prompt.py`.

5. **Generate** — `LLMWrapper` calls Ollama (default) or a user-configured API key. Stakeholder chat fails clearly if no LLM is available (no template fallback).

6. **Respond & save** — JSON includes `response`, `mode_used` (e.g. `vector`, `hybrid:chroma`, `direct`, `compare`), optional `routing`, `llm_used`, optional `debug`, and `conversation_id`.

**UI behavior** (`chat.js`):

- **Desktop** — Conversation list and settings stay in the left pane.
- **Mobile (≤768px)** — Pane is off-canvas; **☰** opens conversations, **+ New chat**, **⚙️ API config**, and sign out.
- **LLM model** dropdown appears when Ollama and/or API keys are configured (`GET /api/config`).
- **👍 / 👎** on assistant messages feed the tweak file when tweak mode is on.

**Comparing retrieval vs direct model:**

| You want… | Example prompt | Mode | Typical `mode_used` |
|-----------|----------------|------|---------------------|
| Vector retrieval | `What worries you most?` | Vector RAG | `vector` |
| Graph retrieval | `Who depends on this milestone?` | Neo4j RAG | `neo4j` |
| Auto routing | `Tell me about the project` | Hybrid RAG | `hybrid:chroma` etc. |
| No retrieval baseline | Same question | Direct Model | `direct` |
| Side-by-side | Select **Compare All** | All four | `compare` |

Domain terms (e.g. `What is a deduction?`) are answered **in character** as the stakeholder would — not as a classroom explainer.

## Data Processing & Chunking Strategy

### Chunking Approach

The system uses a **row-based chunking strategy** optimized for structured Excel data:

1. **Sheet Processing**: Each Excel sheet is processed independently
2. **Row-Level Chunks**: Each row becomes a single document chunk
3. **Text Representation**: All columns in a row are combined into a structured text format:
  ```
   Sheet: Stakeholder
   id: S1
   name: Product Manager
   role: Requirements Owner
   description: Responsible for defining product requirements
  ```

### Supported Sheets

The system processes the following sheet types from the Excel knowledge base:

- **People**: `Stakeholder`, `Client`, `Role`
- **Requirements**: `Requirement`, `Feature`, `FunctioFFnal_Requirement`
- **Planning**: `Goal`, `Timeline`, `Milestone`, `Task`
- **Constraints**: `Constraint`, `Risk`, `Qual_Scenario`
- **Budget**: `Budget`, `Line_Item`
- **Project**: `Project`

### Metadata Enrichment

Each chunk includes rich metadata for filtering and context:

- `sheet`: Source sheet name
- `row`: Original row index
- `sheet_type`: Categorized type (people, requirements, planning, etc.)
- `keywords`: Extracted keywords for better matching

## Embedding Strategy

### Model Selection

- **Model**: `all-MiniLM-L6-v2` from sentence-transformers
- **Dimensions**: 384-dimensional vectors
- **Why this model?**
  - Fast inference (~14,000 sentences/sec)
  - Good semantic understanding for technical documents
  - Balanced performance for structured data
  - Small model size (~80MB)

### Embedding Process

1. **Text Normalization**: Each row is converted to a structured text format
2. **Batch Encoding**: Documents are embedded in batches of 100 for efficiency
3. **Vector Storage**: Embeddings stored in ChromaDB with cosine similarity
4. **Persistence**: Vectors are persisted to disk for reuse across sessions

### Similarity Search

- **Distance Metric**: Cosine similarity (default for ChromaDB)
- **Search Space**: HNSW (Hierarchical Navigable Small World) index for fast approximate nearest neighbor search
- **Result Ranking**: Results sorted by distance (lower = more similar)

## Query Processing & Retrieval

### Query Intent Detection

The system uses keyword-based intent detection to understand what the trainee is asking:

```python
intent_keywords = {
    'Stakeholder': ['stakeholder', 'stakeholders', 'people', 'person', 'who'],
    'Goal': ['goal', 'goals', 'objective', 'objectives', 'want', 'need'],
    'Feature': ['feature', 'features', 'functionality', 'do', 'can'],
    # ... etc
}
```

### Multi-Stage Filtering

1. **Pre-Filtering**: When intent is detected, search is restricted to relevant sheets
2. **Vector Search**: Semantic similarity search within filtered sheets
3. **Post-Filtering**: Additional filtering to remove irrelevant results
4. **Relevance Ranking**: Results sorted by similarity score

### Search Strategy

```python
# Example: Query "Who are the stakeholders?"
1. Detect intent → ['Stakeholder']
2. Filter search → Only search in Stakeholder sheet
3. Vector search → Find similar stakeholder entries
4. Post-filter → Remove any non-stakeholder results
5. Rank & return → Top N most relevant results
```

## Response Generation

Generation is handled by **`LLMWrapper`** — stakeholder chat requires a configured LLM (Ollama or user API key); there is no template fallback.

### Stakeholder persona (all modes)

- One shared prompt in `app/scenario/stakeholder_prompt.py` — natural, in-character, gradual reveal
- Clear definitions tied to **this** project’s workbook
- Bullet list of good follow-up questions for a real stakeholder interview
- Does not use stakeholder openings (`Oh, well…`) or role-play

See [How the chat works](#how-the-chat-works) for the full pipeline. Example eval transcripts: `docs/eval/`.

## Training Workflow

### For Trainees

**During the Conversation:**

1. **Start Conversation**: Begin with an introduction or open-ended question
2. **Ask Questions**: Use natural language to gather information - ask about stakeholders, goals, features, constraints, etc.
3. **Follow Up**: Ask clarifying questions based on responses to fill gaps
4. **Take Notes**: Document what you learn (outside the system) - the stakeholder speaks informally, so you need to capture and structure the information

**After the Conversation:**
5. **Formalize Requirements**: Convert the informal, unstructured responses into formal requirements documentation:

- Identify stakeholders and their roles
- Extract functional and non-functional requirements
- Document goals and objectives
- List constraints and risks
- Structure everything into a proper requirements document format

**Key Challenge**: The stakeholder will speak casually and may not use technical terminology. Your job is to extract the essential information and formalize it.

### Example Training Session

**Conversation:**

```
Trainee: Hi, can you tell me about the project?
Stakeholder: Oh sure! So we're building this system to help manage our operations better. 
            We really need something that can handle changes quickly, especially with 
            regulations and stuff. Does that help?

Trainee: Who else is involved in this project?
Stakeholder: Let me think... There's Sarah, who's the Product Manager. And then there's 
            John, they're the Lead Developer. Also Mike, he's our QA lead. What else 
            do you want to know?

Trainee: What are your main concerns?
Stakeholder: Yeah, there are a few things we're worried about. The system needs to be 
            really reliable, especially if our local infrastructure isn't super stable. 
            Also, we need to keep costs down - hosting, staff, support, all that stuff. 
            Hope that helps!
```

**Trainee's Formalized Requirements (created after the conversation):**

```
STAKEHOLDERS:
- Sarah: Product Manager
- John: Lead Developer  
- Mike: QA Lead

GOALS:
- G1: Build a system to manage operations more effectively
- G2: System must handle changes quickly, particularly regulatory changes

NON-FUNCTIONAL REQUIREMENTS:
- NFR1: System must be highly reliable
- NFR2: System must function in unstable local infrastructure environments
- NFR3: Minimize operational costs (hosting, staff, support)

CONSTRAINTS:
- C1: Local infrastructure may be unstable
- C2: Budget constraints require cost minimization
```

**Note**: The trainee has extracted structured requirements from the informal conversation, identifying stakeholders, goals, non-functional requirements, and constraints.

## Customization

### Adjusting Response Style

To make responses more or less formal, edit the `_generate_informal_response` method in `app/rag_backend.py`:

```python
# More casual
response_parts.append("Yeah, so... ")

# More professional (but still informal)
response_parts.append("Well, from our perspective... ")
```

### Using a Real LLM (Recommended)

The system now supports real LLMs for much more natural, human-like responses. The template-based approach is limited - using a real LLM is the standard RAG approach.

#### Option 1: Ollama (Recommended - Free & Local)

**Ollama** is the easiest way to get high-quality, local LLM responses:

1. **Install Ollama**: Download from [ollama.ai](https://ollama.ai)
2. **Pull a model** (choose one):
  ```bash
   ollama pull llama3.2        # Fast, good quality (recommended)
   ollama pull mistral         # Alternative option
   ollama pull phi3            # Smaller, faster
  ```
3. **Start the server** (Ollama runs automatically):
  ```bash
   # Ollama should start automatically, or:
   ollama serve
  ```
4. **Run your app** (it will auto-detect Ollama):
  ```bash
   python -m app.main
  ```
   Or specify the model:

**Benefits:**

- ✅ Free and runs locally (no API costs)
- ✅ Privacy (data stays on your machine)
- ✅ High-quality, natural responses
- ✅ Works offline

#### Option 2: OpenAI API

For cloud-based LLM (requires API key):

1. **Install OpenAI package**:
  ```bash
   pip install openai
  ```
2. **Set your API key**:
  ```bash
   export OPENAI_API_KEY="your-key-here"
  ```
3. **Run with OpenAI backend**:
  ```bash
   LLM_BACKEND=openai LLM_MODEL=gpt-3.5-turbo python -m app.main
  ```

#### Option 3: Template Fallback

If no LLM is available, the system automatically falls back to template-based generation:

```bash
LLM_BACKEND=template python -m app.main
```

**Note**: Template-based responses are limited in quality and naturalness. A real LLM is strongly recommended.

### Adding More Sheets

Edit `app/rag_backend.py` and modify the `key_sheets` list in the `_load_requirements` method:

```python
key_sheets = [
    'Requirement', 'Feature', 'Stakeholder',
    # Add your sheet names here
]
```

### Changing the Embedding Model

To use a different embedding model:

```python
# In RequirementsRAG.__init__
self.embedding_model = SentenceTransformer('your-model-name')
```

Popular alternatives:

- `all-mpnet-base-v2`: Better quality, slower
- `paraphrase-MiniLM-L6-v2`: Similar to current, optimized for paraphrasing
- `multi-qa-MiniLM-L6-cos-v1`: Optimized for Q&A tasks

## Project Structure

```
.
├── app/
│   ├── main.py              # Entrypoint module (python -m app.main)
│   ├── fix_pytree.py        # Torch/pytree compatibility shim
│   ├── scenario/            # scenario_pack, stakeholder_prompt, direct_model
│   ├── llm_wrapper.py       # Stakeholder LLM generation (no template fallback)
│   ├── llm_registry.py      # Model discovery, dropdown, Ollama name resolution
│   ├── stakeholder_tone.py  # Plain-language post-processing for stakeholders
│   ├── rag_backend.py       # ChromaDB RAG + SimpleLLM template fallback
│   ├── rag_backend_neo4j.py # Neo4j vector + graph RAG
│   ├── mcp/                 # In-process hybrid router (Chroma + Neo4j)
│   │   ├── hybrid.py
│   │   └── router.py
│   ├── api/
│   │   ├── app.py           # FastAPI app and routes
│   │   └── schemas.py       # API request/response models
│   ├── storage/
│   │   └── conversation_store.py # SQLModel + SQLite persistence
│   ├── tweaks/
│   │   └── behavior_tweaks.py # Runtime tweak store logic
│   ├── web/
│   │   ├── templates/
│   │   │   └── index.html   # Jinja2 template for chat UI
│   │   └── static/
│   │       └── components/
│   │           └── chat.js  # Web chat component logic
├── config/
│   ├── behavior/
│   │   └── behavior_tweaks.json # External behavior tweak data

├── setup/
│   ├── chroma/
│   │   └── init_chroma.py   # Chroma setup/warmup script
│   ├── neo4j/
│   │   └── load_graph.py    # Neo4j graph load script
│   ├── users/
│   │   └── manage_users.py  # CLI: seed / list / add users
│   └── eval/
│       └── run_requirements_chat.py  # Scripted chat eval runner
├── docker/
│   └── entrypoint.sh        # Container startup (Chroma seed + uvicorn)
├── docker-compose.yml       # Local stack (+ optional postgres / mcp profiles)
├── docs/
│   ├── SETUP_LLM.md         # LLM setup guide
│   ├── DEPLOY_EASYPANEL.md  # Production on EasyPanel

├── requirements.txt         # Python dependencies
├── .env.example             # Env template (copy to app/.env for local dev)
├── data.xlsx                # Knowledge base (stakeholder information)
├── storage/
│   ├── chroma_db_v2/        # ChromaDB database (gitignored)
│   └── conversations.db     # SQLite chat history (gitignored)
└── README.md                # This file
```

## Technologies Used

- **FastAPI**: Modern web framework for building APIs
- **ChromaDB**: Open-source vector database for embeddings
- **Neo4j**: Graph database for relationship-aware RAG (optional backend)

- **sentence-transformers**: Library for sentence embeddings
- **pandas**: Data manipulation and Excel file processing
- **openpyxl**: Excel file reading library
- **uvicorn**: ASGI server for FastAPI

## Performance Considerations

- **Embedding Speed**: ~14,000 sentences/sec with all-MiniLM-L6-v2
- **Search Speed**: Sub-millisecond with HNSW index
- **Batch Processing**: Documents processed in batches of 100
- **Persistence**: Database persists to disk, no re-indexing needed

## Design Principles

### Why No Source References?

The system is designed for **training**, not document querying. The training objective is to practice:

- **Extracting information from conversation**: Real stakeholders don't provide structured documentation
- **Identifying important information**: Learning to distinguish key requirements from casual conversation
- **Formalizing requirements**: Converting informal input into structured, formal requirements documentation
- **Working without documentation**: In real scenarios, requirements often come from conversations, not documents

If the system showed source references, trainees would skip the critical skill of extracting and structuring information from informal conversation.

### Why Informal Language?

Real stakeholders are often non-technical and speak informally. The system simulates this to:

- **Provide realistic training scenarios**: Mimics actual stakeholder conversations
- **Challenge trainees**: Forces extraction of structured information from unstructured conversation
- **Prepare for real-world**: Most requirements gathering happens through informal conversations
- **Build critical skills**: Trainees learn to ask the right questions and formalize responses

The informal language is intentional - it's the core challenge that makes this effective training.

## LLM Integration

### Why Use a Real LLM?

The template-based approach has significant limitations:

- ❌ Poor grammar and awkward phrasing
- ❌ Limited natural language variation
- ❌ Can't handle complex queries well
- ❌ Feels robotic, not human-like

**Using a real LLM (like Ollama) provides:**

- ✅ Natural, human-like responses
- ✅ Proper grammar automatically
- ✅ Better context understanding
- ✅ More conversational and varied responses
- ✅ Handles edge cases better

### How RAG + LLM Works

1. **Mode** — Vector, Neo4j, hybrid, direct, or compare.
2. **Context** — RAG retrieval or full scenario pack (direct).
3. **Prompting** — Shared stakeholder prompt + context + conversation history.
4. **Generation** — Ollama or user-configured cloud API (required).

See [How the chat works](#how-the-chat-works) for the full request path.

### Recommended Setup

**For best results, use Ollama with llama3.2:**

```bash
# Install Ollama, then:
ollama pull llama3.2
python -m app.main  # Auto-detects Ollama
```

The system will automatically:

- Use Ollama if available
- Fall back to template if Ollama isn't running
- Provide much better responses with LLM

## Limitations & Future Improvements

### Current Limitations

- ~~Template-based response generation~~ ✅ **Fixed with LLM support**
- Row-level chunking (no cross-row context)
- Keyword-based intent detection (could use ML classification)
- No conversation history (stateless queries)
- Fixed response style (could vary by stakeholder personality)

### Potential Improvements

- ✅ ~~Integrate real LLM~~ **Done!** Use Ollama or OpenAI
- Add conversation memory/context for follow-up questions
- Implement multiple stakeholder personas with different communication styles
- Add support for multi-turn conversations with context
- Implement query expansion for better retrieval
- Add confidence scores (internal, not shown to user)
- Support for different training scenarios
- Multi-language support
- Fine-tune LLM prompts for better stakeholder persona

## Neo4j Hybrid Backend (Recommended)

> **Chat “hybrid” mode** (UI / `response_mode=hybrid`) is separate: it **auto-routes** each question to Chroma or Neo4j, or blends both.  
> This section describes the **`RAG_BACKEND=neo4j`** stack: vector search plus graph relationships in one backend.

The system supports a **hybrid Neo4j backend** that combines vector search with graph relationships for superior context retrieval.

### Why Neo4j?

Your Excel file has a **Relationships sheet** with 48 explicit relationships (HAS_CONSTRAINT, SATISFIES, OWNED_BY, etc.). Neo4j leverages these relationships to provide:

1. **Better Context**: When you ask about a stakeholder, it finds related requirements, goals, and constraints via graph traversal
2. **Relationship-Aware Retrieval**: Follows graph paths to find connected information
3. **Hybrid Search**: Combines semantic similarity (vector) with relationship queries (graph)

### Setup Neo4j

1. **Install Neo4j**:
  - Download from [neo4j.com](https://neo4j.com/download/)
  - Or use Docker: `docker run -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/password neo4j:latest`
2. **Start Neo4j**:
  ```bash
   # Desktop: Just launch Neo4j Desktop
   # Docker: Already running if using docker command above
   # Default credentials: neo4j/password (change on first login)
  ```
3. **Install Python package**:
  ```bash
   pip install neo4j
  ```
4. **Configure env** (recommended):
  ```bash
   cp .env.example app/.env
   # Edit app/.env and set:
   RAG_BACKEND=neo4j
   NEO4J_PASSWORD=your_password
  ```
5. **Run the app**:
  ```bash
   python -m app.main
  ```
   Settings load from `app/.env` (then optional project-root `.env`).
   **Alternative: Set environment variables directly:**

### How It Works

**Hybrid Search Process:**

1. **Vector Search**: Find semantically similar nodes using cosine similarity on embeddings
2. **Graph Traversal**: For each result, traverse relationships to find connected nodes
3. **Enhanced Context**: Combine original results with related nodes for richer context

### Current Neo4j Model Structure

The current implementation in `app/rag_backend_neo4j.py` loads the Excel workbook into a graph with:

1. **Node identity**
  - `node_id` from each row's `id` column (required)
  - Nodes are merged by `node_id` (`MERGE (n:{Label} {node_id: $node_id})`)
2. **Node labels (sheet -> label mapping)**
  - `Project` -> `Project`
  - `Stakeholder` -> `Stakeholder`
  - `Client` -> `Client`
  - `Role` -> `Role`
  - `Feature` -> `Feature`
  - `Requirement` -> `Requirement`
  - `FunctioFFnal_Requirement` -> `FunctionalRequirement`
  - `Goal` -> `Goal`
  - `Constraint` -> `Constraint`
  - `Risk` -> `Risk`
  - `Budget` -> `Budget`
  - `Line_Item` -> `LineItem`
  - `Timeline` -> `Timeline`
  - `Milestone` -> `Milestone`
  - `Task` -> `Task`
  - `Qual_Scenario` -> `QualityScenario`
  - Unknown sheets -> `RequirementNode`
3. **Node properties**
  - All Excel columns are copied to properties using lowercase/snake_case keys
  - Common system properties:
    - `node_id`
    - `sheet`
    - `text` (full row serialized as text)
    - `embedding` (vector from `all-MiniLM-L6-v2`)
4. **Relationships**
  - Loaded from the `Relationships` sheet using:
    - `start_id` (source node `node_id`)
    - `end_id` (target node `node_id`)
    - `type` (relationship type, uppercased and spaces replaced by `_`)
  - Cypher pattern:
    - `MATCH (a {node_id: $start_id})`
    - `MATCH (b {node_id: $end_id})`
    - `MERGE (a)-[r:REL_TYPE]->(b)`
5. **Retrieval behavior**
  - Vector retrieval computes cosine similarity over stored `embedding`
  - Top matches are enriched with graph neighbors from one-hop traversals
  - Returned result format: `document`, `metadata`, `distance`

**Example Query Flow:**

```
Query: "What are Sarah's concerns?"

1. Vector search → Find Stakeholder node for "Sarah"
2. Graph traversal → Follow OWNED_BY → Requirements
3. Graph traversal → Follow HAS_RISK → Risks  
4. Graph traversal → Follow HAS_CONSTRAINT → Constraints
5. Return comprehensive context about Sarah's concerns
```

### Comparison: ChromaDB vs Neo4j


| Feature              | ChromaDB               | Neo4j                  |
| -------------------- | ---------------------- | ---------------------- |
| Vector Search        | ✅ Fast                 | ✅ Fast                 |
| Relationship Queries | ❌ Not supported        | ✅ Excellent            |
| Context Quality      | ⭐⭐ Good                | ⭐⭐⭐⭐ Excellent         |
| Setup Complexity     | ⭐ Easy                 | ⭐⭐ Medium              |
| Best For             | Simple semantic search | Relationship-rich data |


**Recommendation**: Use Neo4j if your Excel has relationships (which it does!). The hybrid approach provides much better context for training.

### Response Modes in the Chat UI

Per-message `response_mode` (dropdown in the chat input area):

| Mode | Retrieval | Notes |
|------|-----------|-------|
| `vector` | Chroma only | Stakeholder persona |
| `neo4j` | Neo4j only | Stakeholder persona |
| `hybrid` | Auto-route (`chroma` / `neo4j` / `blend`) | Stakeholder persona |
| `direct` | None (full scenario pack) | Baseline without RAG |
| `compare` | All four independently | Side-by-side labels in one reply |

Assistant messages show a badge (`Vector RAG`, `hybrid → chroma`, `Direct Model`, etc.) and which LLM was used when applicable.

| Hybrid route | Typical questions |
|--------------|-------------------|
| `chroma` | Broad, semantic, narrative (“tell me about goals…”) |
| `neo4j` | Dependencies, paths, timelines, connectivity |
| `blend` | Ambiguous or close router scores |

Backend helpers:

- `GET /api/modes`: shows which modes are available at runtime
- `POST /api/chat` body accepts `response_mode`
- `GET /api/config`: shows runtime configuration, key status, and tweaks file metadata
- `GET /api/conversations`: lists saved conversations
- `GET /api/conversations/{conversation_id}`: loads a conversation with messages

### Runtime Behavior Tweaks (Feedback Loop)

Behavior adjustments are stored in an external JSON file (`config/behavior/behavior_tweaks.json` by default), so they can be customized without code changes and loaded at runtime.

- **Feature flag**: set `TWEAK_MODE_ENABLED=true` to enable tweak mode
- **When disabled**: response tweaks are not applied and `POST /api/feedback` is blocked
- **Tweaks file path**: controlled by `BEHAVIOR_TWEAKS_FILE` (default: `config/behavior/behavior_tweaks.json`)
- **Loaded at runtime**: each response reads current tweaks, so changes apply immediately
- **UI feedback**: each assistant response includes:
  - `👍 Good` (logs positive feedback)
  - `👎 Improve` (captures correction text, optional improved response)
- **Feedback API**: `POST /api/feedback` updates the tweaks file

If a corrected response is provided in feedback, it is saved as a query-specific override. Repeating the same prompt should then return the improved version.

The tweak file currently supports:

- `global` tweaks (replacements, blocked phrases, sentence de-dup)
- `pattern_overrides` for repeatable behavior policies (for example, technical-definition redirection)
- `query_overrides` for exact prompt corrections
- `feedback_log` for audit/history of runtime changes

### Conversation Persistence (SQLModel + SQLite)

Conversation history is now persisted so users can view and continue prior sessions.

- **Storage**: SQLite via SQLModel (`CONVERSATION_DB_URL`, default `sqlite:///./storage/conversations.db`)
- **Continue chat**: send `conversation_id` in `POST /api/chat`
- **New chat**: omit `conversation_id` and the app creates one automatically
- **UI support**: conversation list in the side nav (collapsible drawer on mobile); **+ New chat** clears the active thread without deleting history

### Setup Scripts

- Initialize Chroma store: `python -m setup.chroma.init_chroma`
- Load Neo4j graph: `python -m setup.neo4j.load_graph`
- Start app: `start.bat` (Windows) or `python -m app.main`

### Migration from ChromaDB

If you've been using ChromaDB, switching to Neo4j is easy:

1. Install Neo4j and start it
2. Set `RAG_BACKEND=neo4j` environment variable
3. Restart the app - it will automatically load data into Neo4j
4. Your ChromaDB data remains untouched (you can switch back anytime)

## License

Open source - feel free to modify and use as needed.