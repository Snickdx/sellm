"""
Runtime behavior tweak store for stakeholder response customization.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


DEFAULT_TWEAKS: Dict[str, Any] = {
    "version": 1,
    "last_updated": _utc_now(),
    "global": {
        "dedupe_sentences": True,
        "replacements": {
            "system shall": "we need it to",
            "System shall": "We need it to",
            "the system shall": "we need the system to",
            "The system shall": "We need the system to",
        },
        "blocked_phrases": [],
    },
    "query_overrides": [],
    "pattern_overrides": [],
    "feedback_log": [],
}


class BehaviorTweaksStore:
    def __init__(self, path: str):
        self.path = path
        self._ensure_file()

    def _ensure_file(self) -> None:
        if os.path.exists(self.path):
            return
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_TWEAKS, f, indent=2)

    def load(self) -> Dict[str, Any]:
        self._ensure_file()
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if not isinstance(data, dict):
                    return dict(DEFAULT_TWEAKS)
                return data
        except Exception:
            return dict(DEFAULT_TWEAKS)

    def save(self, data: Dict[str, Any]) -> None:
        data["last_updated"] = _utc_now()
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def _normalize_query(self, query: str) -> str:
        return " ".join(query.lower().strip().split())

    def _matches_pattern(self, query: str, rule: Dict[str, Any]) -> bool:
        candidates = [self._normalize_query(query)]
        pattern_values = rule.get("match_any", [])
        if not isinstance(pattern_values, list):
            return False
        for pattern in pattern_values:
            text = self._normalize_query(str(pattern))
            if not text:
                continue
            if any(text in candidate for candidate in candidates):
                return True
        return False

    def _dedupe_sentences(self, text: str) -> str:
        parts = [p.strip() for p in text.replace("?", ".").replace("!", ".").split(".")]
        seen = set()
        kept = []
        for part in parts:
            if not part:
                continue
            key = part.lower()
            if key in seen:
                continue
            seen.add(key)
            kept.append(part)
        if not kept:
            return text
        result = ". ".join(kept).strip()
        if not result.endswith((".", "?", "!")):
            result += "."
        return result

    def apply_to_response(self, query: str, response: str) -> str:
        data = self.load()
        norm_query = self._normalize_query(query)

        # Query-specific hard override (highest priority).
        for rule in data.get("query_overrides", []):
            if rule.get("query") == norm_query and rule.get("response"):
                return str(rule["response"]).strip()

        # Pattern-level override (second priority).
        for rule in data.get("pattern_overrides", []):
            if self._matches_pattern(query, rule) and rule.get("response"):
                return str(rule["response"]).strip()

        output = response
        global_cfg = data.get("global", {})

        for old, new in global_cfg.get("replacements", {}).items():
            output = output.replace(old, new)

        for phrase in global_cfg.get("blocked_phrases", []):
            output = output.replace(phrase, "")

        if global_cfg.get("dedupe_sentences", False):
            output = self._dedupe_sentences(output)

        return " ".join(output.split())

    def update_from_feedback(
        self,
        query: str,
        response: str,
        feedback: str,
        desired_response: Optional[str] = None,
        mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        data = self.load()
        global_cfg = data.setdefault("global", {})
        global_cfg.setdefault("replacements", {})
        global_cfg.setdefault("blocked_phrases", [])
        data.setdefault("query_overrides", [])
        data.setdefault("feedback_log", [])

        changes: List[str] = []
        feedback_lower = (feedback or "").lower()

        if desired_response and desired_response.strip():
            norm_query = self._normalize_query(query)
            overrides = data["query_overrides"]
            found = False
            for rule in overrides:
                if rule.get("query") == norm_query:
                    rule["response"] = desired_response.strip()
                    found = True
                    break
            if not found:
                overrides.append(
                    {
                        "query": norm_query,
                        "response": desired_response.strip(),
                        "created_at": _utc_now(),
                    }
                )
            changes.append("Saved query-specific override response")

        if "repeat" in feedback_lower or "repet" in feedback_lower:
            if not global_cfg.get("dedupe_sentences", False):
                global_cfg["dedupe_sentences"] = True
                changes.append("Enabled sentence de-duplication")

        if "system shall" in response.lower() or "formal" in feedback_lower:
            if "system shall" not in global_cfg["replacements"]:
                global_cfg["replacements"]["system shall"] = "we need it to"
            if "the system shall" not in global_cfg["replacements"]:
                global_cfg["replacements"]["the system shall"] = "we need the system to"
            changes.append("Added natural-language rewrite for formal requirement phrases")

        if "not stakeholder" in feedback_lower or "too technical" in feedback_lower:
            phrase = "system shall"
            if phrase not in [p.lower() for p in global_cfg.get("blocked_phrases", [])]:
                global_cfg["blocked_phrases"].append(phrase)
                changes.append("Added stakeholder-tone guard phrase block")

        data["feedback_log"].append(
            {
                "time": _utc_now(),
                "query": query,
                "mode": mode,
                "feedback": feedback,
                "desired_response": desired_response,
                "response_excerpt": response[:240],
                "changes": changes,
            }
        )

        self.save(data)
        return {"changes": changes, "last_updated": data["last_updated"]}
