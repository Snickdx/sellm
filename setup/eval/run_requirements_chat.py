"""Run a short stakeholder requirements chat and save transcript."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

_REPO = Path(__file__).resolve().parents[2]
load_dotenv(_REPO / "app" / ".env")

BASE = os.getenv("EVAL_BASE_URL", "http://127.0.0.1:8000")
USER = os.getenv("EVAL_USER", "snick")
PASSWORD = os.getenv("EVAL_PASSWORD", "badPassword1")
OUT_DIR = _REPO / "docs" / "eval"

TURNS = [
    ("vector", "Who's involved in this project from your perspective?"),
    ("vector", "What are we trying to accomplish overall?"),
    ("vector", "any other user types?"),
    ("vector", "What happens when a new admin user signs up?"),
    ("vector", "What worries you most about this project?"),
    ("hybrid", "define a deduction"),
    ("coach", "explain what a benefit plan is in this project"),
]


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    login = requests.post(
        f"{BASE}/api/auth/login",
        json={"username": USER, "password": PASSWORD},
        timeout=30,
    )
    login.raise_for_status()
    token = login.json()["token"]
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    conversation_id = None
    transcript = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "base_url": BASE,
        "user": USER,
        "turns": [],
    }

    for mode, question in TURNS:
        body = {
            "message": question,
            "response_mode": mode,
            "conversation_id": conversation_id,
        }
        resp = requests.post(f"{BASE}/api/chat", json=body, headers=headers, timeout=180)
        if not resp.ok:
            transcript["turns"].append(
                {
                    "mode": mode,
                    "question": question,
                    "error": resp.text,
                    "status": resp.status_code,
                }
            )
            continue
        data = resp.json()
        conversation_id = data.get("conversation_id") or conversation_id
        transcript["turns"].append(
            {
                "mode": mode,
                "question": question,
                "response": data.get("response"),
                "mode_used": data.get("mode_used"),
                "llm_used": data.get("llm_used"),
                "routing": data.get("routing"),
            }
        )

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = OUT_DIR / f"requirements_chat_{stamp}.json"
    md_path = OUT_DIR / f"requirements_chat_{stamp}.md"
    json_path.write_text(json.dumps(transcript, indent=2), encoding="utf-8")

    lines = [
        f"# Requirements chat run — {transcript['run_at']}",
        "",
        f"User: {USER} | Base: {BASE}",
        "",
    ]
    for i, turn in enumerate(transcript["turns"], 1):
        lines.append(f"## Turn {i} — mode `{turn.get('mode')}`")
        lines.append(f"**Question:** {turn.get('question')}")
        if turn.get("error"):
            lines.append(f"**Error ({turn.get('status')}):** {turn.get('error')}")
        else:
            lines.append(f"**Mode used:** {turn.get('mode_used')}")
            if turn.get("llm_used"):
                lines.append(f"**LLM:** {turn.get('llm_used')}")
            lines.append(f"**Response:**\n\n{turn.get('response')}")
        lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")

    print(json_path)
    print(md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
