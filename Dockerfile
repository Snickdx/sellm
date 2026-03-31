# Minimal CPU image for EasyPanel / generic Docker hosts.
# Set env: CONVERSATION_DB_URL or DATABASE_URL (PostgreSQL on EasyPanel), OPENAI_API_KEY,
# EXCEL_FILE, CHROMA_PERSIST_DIRECTORY (volume recommended for Chroma), NEO4J_* if used.

FROM python:3.11-slim-bookworm

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p storage

EXPOSE 8000

CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}"]
