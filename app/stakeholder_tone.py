"""Plain-language pass for non-technical stakeholder voice."""

from __future__ import annotations

import re
from typing import List, Tuple

# (pattern, replacement) — applied in order; use regex with IGNORECASE
_PLAIN_LANGUAGE: List[Tuple[str, str]] = [
    (r"\brole-?based access control\b", "who gets to see and do what"),
    (r"\bRBAC\b", "who can access what"),
    (r"\bauthentication\b", "signing in"),
    (r"\bauthorization\b", "permission"),
    (r"\badministrative users?\b", "back-office staff"),
    (r"\bregistration process\b", "sign-up process"),
    (r"\bregistration\b", "sign-up"),
    (r"\btokens?\b", "confirmation link or code in the email"),
    (r"\bAPIs?\b", "hooks to other systems"),
    (r"\bendpoint\b", "connection point"),
    (r"\bdatabase schema\b", "how the data is organized"),
    (r"\bvector database\b", "search index"),
    (r"\bembeddings?\b", "search matching"),
    (r"\bNeo4j\b", "relationship map"),
    (r"\bChromaDB\b", "document search"),
    (r"\bLLM\b", "AI assistant"),
    (r"\bpresentating\b", "showing"),
    (r"\breveiving\b", "getting"),
    (r"\btoekn\b", "link"),
    (r"\bGoal\s+G\d+\b", ""),
    (r"\bthe person interviewing me\b", ""),
    (r"\bperson interviewing me\b", ""),
    (r"\bbeing interviewed\b", "talking with you"),
]


def apply_plain_language(text: str) -> str:
    """Rewrite common technical terms into stakeholder-friendly wording."""
    if not text:
        return text
    out = text
    for pattern, replacement in _PLAIN_LANGUAGE:
        out = re.sub(pattern, replacement, out, flags=re.IGNORECASE)
    return " ".join(out.split())


STAKEHOLDER_PROMPT_RULES = """
- You are NOT technical: never say token, API, RBAC, authentication, authorization, endpoint, schema, or similar jargon.
- Say "confirmation link or code in the email" instead of token; "signing in" instead of authentication; "who can access what" instead of role-based access control.
- Describe user types in business terms (e.g. admin staff, regular users, managers) not IT terms.
- If the project notes use technical words, translate them into everyday language the way a payroll or HR person would speak.
""".strip()
