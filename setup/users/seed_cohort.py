"""
Seed a training cohort of 20 users with per-user token limits and write credentials CSV.

Usage:
  python -m setup.users.seed_cohort
  python -m setup.users.seed_cohort --limit 50000 --count 20
  python -m setup.users.seed_cohort --csv setup/users/cohort_credentials.csv
"""

from __future__ import annotations

import argparse
import csv
import os
import secrets
import string
from pathlib import Path

from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_REPO_ROOT / "app" / ".env")
load_dotenv(_REPO_ROOT / ".env")

from app.storage.conversation_store import ROLE_STUDENT, ConversationStore  # noqa: E402

DEFAULT_CSV = _REPO_ROOT / "setup" / "users" / "cohort_credentials.csv"


def _store() -> ConversationStore:
    url = (
        os.getenv("CONVERSATION_DB_URL")
        or os.getenv("DATABASE_URL")
        or "sqlite:///./storage/conversations.db"
    )
    store = ConversationStore(url)
    store.init()
    return store


def _password(length: int = 12) -> str:
    alphabet = string.ascii_letters + string.digits
    # Avoid ambiguous chars
    alphabet = alphabet.replace("O", "").replace("0", "").replace("l", "").replace("I", "").replace("1", "")
    return "".join(secrets.choice(alphabet) for _ in range(length))


def seed_cohort(
    *,
    count: int = 20,
    token_limit: int = 15_000,
    csv_path: Path = DEFAULT_CSV,
    prefix: str = "trainee",
    reset_usage: bool = True,
    group_name: str | None = None,
) -> list[dict]:
    store = _store()
    rows: list[dict] = []
    for i in range(1, count + 1):
        username = f"{prefix}{i:02d}"
        password = _password()
        user = store.create_user(
            username,
            password,
            token_limit=token_limit,
            reset_usage=reset_usage,
            group_name=group_name,
            role=ROLE_STUDENT,
        )
        rows.append(
            {
                "username": user.username,
                "password": password,
                "user_id": user.id,
                "role": getattr(user, "role", None) or ROLE_STUDENT,
                "group_name": getattr(user, "group_name", None) or "",
                "token_limit": int(user.token_limit or token_limit),
                "tokens_used": int(user.tokens_used or 0),
            }
        )

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["username", "password", "user_id", "role", "group_name", "token_limit", "tokens_used"],
        )
        writer.writeheader()
        writer.writerows(rows)

    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed cohort users + credentials CSV")
    parser.add_argument("--count", type=int, default=20, help="Number of users (default 20)")
    parser.add_argument(
        "--limit",
        type=int,
        default=int(os.getenv("USER_TOKEN_LIMIT", "15000")),
        help="Token limit per user (default USER_TOKEN_LIMIT or 15000)",
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=DEFAULT_CSV,
        help=f"Output credentials CSV (default {DEFAULT_CSV})",
    )
    parser.add_argument("--prefix", default="trainee", help="Username prefix (default trainee)")
    parser.add_argument(
        "--group",
        default=None,
        help="Assign all cohort users to this group label (e.g. morning)",
    )
    parser.add_argument(
        "--keep-usage",
        action="store_true",
        help="Do not reset tokens_used when updating existing users",
    )
    args = parser.parse_args(argv)

    rows = seed_cohort(
        count=args.count,
        token_limit=args.limit,
        csv_path=args.csv,
        prefix=args.prefix,
        reset_usage=not args.keep_usage,
        group_name=args.group,
    )
    print(f"Seeded {len(rows)} users with token_limit={args.limit}")
    if args.group:
        print(f"Group assigned: {args.group}")
    print(f"Credentials written to {args.csv.resolve()}")
    for row in rows:
        print(f"  {row['username']}\tlimit={row['token_limit']}\tused={row['tokens_used']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
