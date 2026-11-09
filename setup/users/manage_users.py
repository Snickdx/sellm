"""
Add or list app login users (SQLite / Postgres per CONVERSATION_DB_URL).

Examples:
  python -m setup.users.manage_users seed
  python -m setup.users.manage_users list
  python -m setup.users.manage_users add snick mySecretPass

Cohort of 20 trainees (credentials CSV):
  python -m setup.users.seed_cohort
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
        limit = getattr(user, "token_limit", None)
        used = getattr(user, "tokens_used", None)
        role = getattr(user, "role", None) or ("admin" if getattr(user, "is_admin", False) else "student")
        group = getattr(user, "group_name", None) or "-"
        print(
            f"{user.id}\t{user.username}\t{role}\tgroup={group}\t"
            f"limit={limit}\tused={used}\t{user.created_at.isoformat()}"
        )
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    store = _store()
    before = {u.username for u in store.list_users()}
    user = store.create_user(
        args.username,
        args.password,
        is_admin=bool(args.admin) if getattr(args, "admin", False) else None,
        group_name=getattr(args, "group", None),
    )
    action = "Updated" if user.username in before else "Created"
    role = "admin" if getattr(user, "is_admin", False) else "user"
    print(f"{action} user '{user.username}' (id={user.id}, {role})")
    return 0


def cmd_promote(args: argparse.Namespace) -> int:
    store = _store()
    users = {u.username: u for u in store.list_users()}
    username = args.username.strip().lower()
    user = users.get(username)
    if not user:
        print(f"User '{username}' not found", file=sys.stderr)
        return 1
    updated = store.update_user(user.id, is_admin=not bool(args.revoke))
    state = "admin" if updated and updated.is_admin else "user"
    print(f"Set '{username}' → {state}")
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
    p_add.add_argument("--admin", action="store_true", help="Grant admin role")
    p_add.add_argument("--group", default=None, help="Assign group/cohort label")
    p_add.set_defaults(func=cmd_add)

    p_promote = sub.add_parser("promote", help="Grant or revoke admin for a user")
    p_promote.add_argument("username")
    p_promote.add_argument("--revoke", action="store_true", help="Remove admin role")
    p_promote.set_defaults(func=cmd_promote)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
