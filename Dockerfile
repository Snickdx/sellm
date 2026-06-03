# CPU image for EasyPanel / generic Docker hosts.
# Chroma is pre-built at image build time; entrypoint re-indexes if the persist dir is empty.
# See docs/DEPLOY_EASYPANEL.md

FROM python:3.11-slim-bookworm

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app \
    PORT=8000 \
    EXCEL_FILE=/app/data.xlsx \
    CHROMA_PERSIST_DIRECTORY=/app/storage/chroma_db_v2

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p storage \
    && python -m setup.chroma.init_chroma

RUN chmod +x docker/entrypoint.sh

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.getenv(\"PORT\", \"8000\")}/api/health', timeout=5)"

ENTRYPOINT ["/app/docker/entrypoint.sh"]
