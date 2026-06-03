#!/bin/sh
set -e

CHROMA_DIR="${CHROMA_PERSIST_DIRECTORY:-/app/storage/chroma_db_v2}"

# Empty volume mounts hide image-baked Chroma; rebuild index when store is absent.
if [ ! -f "${CHROMA_DIR}/chroma.sqlite3" ]; then
  echo "Chroma store missing or empty — building index..."
  python -m setup.chroma.init_chroma
fi

exec uvicorn app:app --host 0.0.0.0 --port "${PORT:-8000}"
