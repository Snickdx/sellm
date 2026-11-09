"""Reset tokens_used to 0 for all (or matching) users."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_dotenv() -> None:
    env = ROOT / "app" / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reset user tokens_used to 0")
    parser.add_argument(
        "--prefix",
        default="",
        help="Only reset usernames starting with this prefix (default: all users)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show who would be reset without writing",
    )
    args = parser.parse_args(argv)

    _load_dotenv()
    from sqlmodel import Session, select
    from app.storage.conversation_store import ConversationStore, User

    url = os.getenv("CONVERSATION_DB_URL") or "sqlite:///./storage/conversations.db"
    store = ConversationStore(url)
    store.init()

    with Session(store.engine) as session:
        users = list(session.exec(select(User).order_by(User.id)).all())
        changed = 0
        for user in users:
            if args.prefix and not user.username.startswith(args.prefix):
                continue
            before = int(user.tokens_used or 0)
            print(f"{user.id}\t{user.username}\tused={before}\tlimit={user.token_limit}")
            if before == 0:
                continue
            if not args.dry_run:
                user.tokens_used = 0
                session.add(user)
            changed += 1
        if not args.dry_run:
            session.commit()
        print(f"{'Would reset' if args.dry_run else 'Reset'} {changed} users")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
