"""
Runtime behavior tweak store for stakeholder response customization.
"""

from __future__ import annotations

import copy
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


# Pretty-printed for editing and readable git diffs (payload is also summarized for reflection prompts).
_JSON_WRITE_KWARGS = {"ensure_ascii": False, "indent": 2, "allow_nan": False}

# Extra stakeholder system instructions (injected into the LLM per turn), separate from post-processing.
_MAX_SYSTEM_SUFFIX_CHARS = 2500


def _write_tweaks_json(path: str, data: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, **_JSON_WRITE_KWARGS)
        f.write("\n")


DEFAULT_TWEAKS: Dict[str, Any] = {
    "version": 1,
    "last_updated": _utc_now(),
    "prompt": {
        "system_suffix": "",
    },
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
    "reflection_log": [],
}


class BehaviorTweaksStore:
    def __init__(self, path: str):
        self.path = path
        self._ensure_file()

    def _ensure_file(self) -> None:
        if os.path.exists(self.path):
            return
        directory = os.path.dirname(self.path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        _write_tweaks_json(self.path, copy.deepcopy(DEFAULT_TWEAKS))

    def load(self) -> Dict[str, Any]:
        self._ensure_file()
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if not isinstance(data, dict):
                    return copy.deepcopy(DEFAULT_TWEAKS)
                if "prompt" not in data or not isinstance(data.get("prompt"), dict):
                    data = dict(data)
                    data["prompt"] = {"system_suffix": ""}
                else:
                    data["prompt"].setdefault("system_suffix", "")
                return data
        except Exception:
            return copy.deepcopy(DEFAULT_TWEAKS)

    def save(self, data: Dict[str, Any]) -> None:
        data["last_updated"] = _utc_now()
        _write_tweaks_json(self.path, data)

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

        for rule in data.get("query_overrides", []):
            if rule.get("query") == norm_query and rule.get("response"):
                return str(rule["response"]).strip()

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

    def system_suffix_for_llm(self) -> str:
        """Text appended to stakeholder system / RAG instructions (not post-processed)."""
        data = self.load()
        p = data.get("prompt") or {}
        if not isinstance(p, dict):
            return ""
        raw = p.get("system_suffix")
        if raw is None:
            return ""
        text = str(raw).strip()
        if not text:
            return ""
        return self._truncate(text, _MAX_SYSTEM_SUFFIX_CHARS)

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

    @staticmethod
    def _truncate(text: str, max_len: int) -> str:
        text = " ".join(text.strip().split())
        if len(text) <= max_len:
            return text
        return text[: max_len - 3] + "..."

    def apply_reflection_patch(self, llm_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Merge a compact reflection patch from the meta-LLM into the tweak file.
        llm_result: { "performance_notes"?: str, "patch": { "global"?, "query_overrides_add"?, "pattern_overrides_add"? } }
        """
        data = self.load()
        global_cfg = data.setdefault("global", {})
        global_cfg.setdefault("replacements", {})
        global_cfg.setdefault("blocked_phrases", [])
        data.setdefault("query_overrides", [])
        data.setdefault("pattern_overrides", [])
        data.setdefault("feedback_log", [])
        data.setdefault("reflection_log", [])

        changes: List[str] = []
        patch = llm_result.get("patch") if isinstance(llm_result.get("patch"), dict) else {}
        g = patch.get("global") if isinstance(patch.get("global"), dict) else {}

        max_resp = 480
        max_q = 50
        max_pat = 25

        reps = g.get("replacements")
        if isinstance(reps, dict):
            for k, v in reps.items():
                if not k or v is None:
                    continue
                ks, vs = str(k).strip(), str(v).strip()
                if not ks or not vs:
                    continue
                global_cfg["replacements"][ks] = self._truncate(vs, 200)
            if reps:
                changes.append("global:replacements")

        if "dedupe_sentences" in g and g["dedupe_sentences"] is not None:
            global_cfg["dedupe_sentences"] = bool(g["dedupe_sentences"])
            changes.append("global:dedupe_sentences")

        for phrase in g.get("blocked_phrases_add") or []:
            p = self._truncate(str(phrase).strip(), 120)
            if not p:
                continue
            lower = [x.lower() for x in global_cfg["blocked_phrases"]]
            if p.lower() not in lower:
                global_cfg["blocked_phrases"].append(p)
        if g.get("blocked_phrases_add"):
            changes.append("global:blocked_phrases_add")

        for phrase in g.get("blocked_phrases_remove") or []:
            p = str(phrase).strip().lower()
            if not p:
                continue
            global_cfg["blocked_phrases"] = [x for x in global_cfg["blocked_phrases"] if x.lower() != p]
        if g.get("blocked_phrases_remove"):
            changes.append("global:blocked_phrases_remove")

        for item in patch.get("query_overrides_add") or []:
            if not isinstance(item, dict):
                continue
            q = item.get("query") or item.get("query_norm") or ""
            norm = self._normalize_query(str(q))
            resp = self._truncate(str(item.get("response") or "").strip(), max_resp)
            if not norm or not resp:
                continue
            found = False
            for rule in data["query_overrides"]:
                if rule.get("query") == norm:
                    rule["response"] = resp
                    rule["updated_at"] = _utc_now()
                    found = True
                    break
            if not found and len(data["query_overrides"]) < max_q:
                data["query_overrides"].append(
                    {"query": norm, "response": resp, "created_at": _utc_now()}
                )
                changes.append(f"query_override:{norm[:40]!r}")
        if patch.get("query_overrides_add"):
            changes.append("query_overrides:merged")

        for rule in patch.get("pattern_overrides_add") or []:
            if not isinstance(rule, dict):
                continue
            ma = rule.get("match_any")
            if not isinstance(ma, list) or not ma:
                continue
            resp = self._truncate(str(rule.get("response") or "").strip(), max_resp)
            if not resp:
                continue
            if len(data["pattern_overrides"]) >= max_pat:
                break
            data["pattern_overrides"].append(
                {
                    "match_any": [str(x).strip() for x in ma if str(x).strip()][:12],
                    "response": resp,
                }
            )
            changes.append("pattern_override:add")
        if patch.get("pattern_overrides_add"):
            changes.append("pattern_overrides:merged")

        p_patch = patch.get("prompt") if isinstance(patch.get("prompt"), dict) else None
        if p_patch is not None and "system_suffix" in p_patch:
            suf = p_patch.get("system_suffix")
            data.setdefault("prompt", {})["system_suffix"] = self._truncate(
                str(suf if suf is not None else "").strip(),
                _MAX_SYSTEM_SUFFIX_CHARS,
            )
            changes.append("prompt:system_suffix")

        data["query_overrides"] = data["query_overrides"][-max_q:]
        data["pattern_overrides"] = data["pattern_overrides"][-max_pat:]
        data["feedback_log"] = data["feedback_log"][-80:]

        notes = llm_result.get("performance_notes")
        if isinstance(notes, str) and notes.strip():
            data["reflection_log"].append(
                {"time": _utc_now(), "notes": self._truncate(notes.strip(), 400)}
            )
            data["reflection_log"] = data["reflection_log"][-15:]
            changes.append("reflection_log:append")

        self.save(data)
        return {"changes": changes, "last_updated": data["last_updated"]}

