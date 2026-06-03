"""
Add or list app login users (SQLite / Postgres per CONVERSATION_DB_URL).

Examples:
  python -m setup.users.manage_users seed
  python -m setup.users.manage_users list
  python -m setup.users.manage_users add snick mySecretPass
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_REPO_ROOT / "app" / ".env")
load_dotenv(_REPO_ROOT / ".env")

from app.storage.conversation_store import ConversationStore  # noqa: E402


def _store() -> ConversationStore:
    url = (
        os.getenv("CONVERSATION_DB_URL")
        or os.getenv("DATABASE_URL")
        or "sqlite:///./storage/conversations.db"
    )
    store = ConversationStore(url)
    store.init()
    return store


def cmd_seed(_: argparse.Namespace) -> int:
    store = _store()
    created = store.seed_users()
    if created:
        print("Created users:", ", ".join(created))
    else:
        print("All default users already exist.")
    print("Default accounts (if newly created use these passwords):")
    for username, _password in ConversationStore.DEFAULT_USERS:
        print(f"  - {username}")
    return 0


def cmd_list(_: argparse.Namespace) -> int:
    store = _store()
    users = store.list_users()
    if not users:
        print("No users in database. Run: python -m setup.users.manage_users seed")
        return 0
    for user in users:
        print(f"{user.id}\t{user.username}\t{user.created_at.isoformat()}")
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    store = _store()
    before = {u.username for u in store.list_users()}
    user = store.create_user(args.username, args.password)
    action = "Updated" if user.username in before else "Created"
    print(f"{action} user '{user.username}' (id={user.id})")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage Requirements Chatbot login users")
    sub = parser.add_subparsers(dest="command", required=True)

    p_seed = sub.add_parser("seed", help="Insert default training users if missing")
    p_seed.set_defaults(func=cmd_seed)

    p_list = sub.add_parser("list", help="List users in the database")
    p_list.set_defaults(func=cmd_list)

    p_add = sub.add_parser("add", help="Add a user or reset password if username exists")
    p_add.add_argument("username")
    p_add.add_argument("password")
    p_add.set_defaults(func=cmd_add)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
