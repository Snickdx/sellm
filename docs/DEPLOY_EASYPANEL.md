# Deploying sellm on EasyPanel (Docker)

This app is a single-container FastAPI service. EasyPanel builds from the repo-root `Dockerfile`. The image **pre-builds the Chroma index** at build time; at startup, `docker/entrypoint.sh` re-indexes only if the persist directory is empty (e.g. a fresh volume mount).

## Architecture (production)

```
Browser → EasyPanel proxy (443) → sellm container :8000
                                      ├─ PostgreSQL (EasyPanel DB service) — conversations
                                      ├─ volume /app/storage — Chroma index + optional SQLite
                                      └─ baked-in or mounted data.xlsx — RAG knowledge base
```

| Concern | Recommendation |
|--------|------------------|
| Conversations | **PostgreSQL** service in the same EasyPanel project (`CONVERSATION_DB_URL` or `DATABASE_URL`) |
| Vector index (Chroma) | **Volume** mounted at `/app/storage` |
| LLM | **`openai`** + `OPENAI_API_KEY` (Ollama is not available inside the app container unless you add a separate Ollama service) |
| Excel knowledge | Ship `data.xlsx` in the image (default) or mount at `/app/data.xlsx` and set `EXCEL_FILE` |

## EasyPanel setup

### 1. Create an App service

1. New **App** → connect this Git repository.
2. **Build** tab → method **Dockerfile**, path **`Dockerfile`** (repo root).
3. Save and **Deploy** (first **build** is slow: PyTorch, embeddings, and Chroma indexing run in the image build).

### 2. Domain & proxy

- **Domain & Proxy** → proxy port **`8000`** (or whatever you set in `PORT`).
- Enable HTTPS on your domain as usual in EasyPanel.

### 3. Environment variables

Use the **Environment** tab (not a committed `.env`). Minimum for a working cloud deployment:

```env
PORT=8000
EXCEL_FILE=/app/data.xlsx
CHROMA_PERSIST_DIRECTORY=/app/storage/chroma_db_v2
CONVERSATION_DB_URL=postgresql+psycopg2://USER:PASSWORD@HOST:5432/DATABASE
LLM_BACKEND=openai
LLM_MODEL=gpt-4o-mini
OPENAI_API_KEY=sk-...
RAG_BACKEND=chromadb
TWEAK_MODE_ENABLED=false
```

- `CONVERSATION_DB_URL` **or** `DATABASE_URL` — EasyPanel Postgres often exposes `postgres://...`; the app normalizes that to `postgresql+psycopg2://...`.
- Use the **internal** DB hostname from EasyPanel (e.g. service name), not `localhost`.

See [`.env.example`](../.env.example) and [`app/.env.example`](../app/.env.example) for all options.

### 4. Persistent storage (required)

Without a volume, Chroma data is lost on every redeploy.

| Mount name | mountPath | Purpose |
|------------|-----------|---------|
| `storage` | `/app/storage` | Chroma DB + SQLite if you use file DB |

Redeploy after adding mounts.

### 5. PostgreSQL (recommended)

1. Add a **PostgreSQL** service in the same project.
2. Copy its connection URL into `CONVERSATION_DB_URL`.
3. Tables are created automatically on startup (`ConversationStore.init()`).

### 6. Health check

The image exposes `GET /api/health`. EasyPanel can use that path for monitoring. Chroma is indexed during the Docker **build**; startup is usually faster unless an empty volume triggers a one-time re-index in the entrypoint.

## Local Docker parity

```bash
# App only (SQLite + volume)
docker compose up --build

# App + Postgres
docker compose --profile postgres up --build
# Set in .env: CONVERSATION_DB_URL=postgresql+psycopg2://sellm:sellm@postgres:5432/sellm
```

## Project layout (deployment-relevant)

```
sellm/
├── Dockerfile              # EasyPanel build
├── docker-compose.yml      # local/staging reference
├── requirements.txt
├── data.xlsx               # default knowledge file (in image)
├── config/behavior/        # tweak JSON (optional)
├── app/
│   ├── api/app.py          # FastAPI app + env loading
│   ├── main.py             # python -m app.main (local)
│   └── .env.example        # local dev template
├── setup/                  # one-off init (Chroma, Neo4j)
│   ├── chroma/init_chroma.py
│   └── neo4j/load_graph.py
├── docker/entrypoint.sh    # startup: seed Chroma if needed, then uvicorn
└── storage/                # gitignored; use volume in production
```

## One-off operations

Warm Chroma without starting the server (run in **Launcher** or a one-off container with the same image, env, and `/app/storage` mount):

```bash
python -m setup.chroma.init_chroma
```

## Troubleshooting

| Symptom | Likely cause |
|--------|----------------|
| 502 / unhealthy during deploy | First deploy after empty volume re-indexes Chroma in entrypoint; wait for `/api/health` |
| Empty or wrong answers | `data.xlsx` missing or wrong `EXCEL_FILE` path |
| Conversations lost | SQLite on ephemeral disk — use Postgres + volume |
| RAG reset after redeploy | No volume on `/app/storage` |
| Neo4j errors | `neo4j` package not in `requirements.txt` by default; use Chroma or uncomment dependency |

## Security notes

- Do not commit `app/.env` or API keys.
- Set secrets only in EasyPanel **Environment**.
- `allow_origins=["*"]` in the API is convenient for training; restrict behind your domain or a reverse proxy if needed.
