"""
Import classlist.csv into the ClassStudent roster table.

Usage:
  python -m setup.users.import_classlist
  python -m setup.users.import_classlist --csv classlist.csv
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_REPO_ROOT / "app" / ".env")
load_dotenv(_REPO_ROOT / ".env")

from app.api.roster import _parse_classlist_csv, _upsert_roster  # noqa: E402
from app.db import configure_engine  # noqa: E402
from app.storage.conversation_store import ConversationStore  # noqa: E402
import app.models  # noqa: F401,E402
from sqlmodel import Session, SQLModel  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import classlist.csv into roster")
    parser.add_argument(
        "--csv",
        type=Path,
        default=_REPO_ROOT / "classlist.csv",
        help="Path to class list CSV",
    )
    args = parser.parse_args(argv)
    if not args.csv.is_file():
        raise SystemExit(f"Missing CSV: {args.csv}")

    url = (
        os.getenv("CONVERSATION_DB_URL")
        or os.getenv("DATABASE_URL")
        or "sqlite:///./storage/conversations.db"
    )
    store = ConversationStore(url)
    store.init()
    configure_engine(store.engine)
    SQLModel.metadata.create_all(store.engine)

    raw = args.csv.read_text(encoding="utf-8-sig")
    rows = _parse_classlist_csv(raw)
    with Session(store.engine) as db:
        result = _upsert_roster(db, rows)
    print(f"Imported roster from {args.csv}")
    print(f"  created={result.created} updated={result.updated} total={result.total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
