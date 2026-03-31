"""
Session reflection: compact transcript + tweak snapshot for meta-LLM, JSON parse helpers.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple


REFLECTION_SYSTEM = """You are a tuning assistant for a requirements-gathering chatbot that simulates a non-technical stakeholder.
The bot uses a JSON tweak file with this shape (keys only; values abbreviated):
- global.replacements: phrase -> friendlier phrase
- global.blocked_phrases: substrings to strip from model output
- global.dedupe_sentences: boolean
- query_overrides: {query: normalized user text, response: fixed assistant reply for that exact query}
- pattern_overrides: {match_any: [substrings], response: fixed reply when any match}

Your job: read the USER message (compact transcript + current tweak summary). Reflect on stakeholder realism, repetition, formality, and off-topic answers. Propose ONLY minimal, high-value edits.

Use the right mechanism:
- patch.global (replacements, blocked_phrases, dedupe): deterministic post-processing on the model output.
- patch.prompt.system_suffix: short extra instructions merged into the stakeholder system prompt at generation time (for tone/behavior the model should follow proactively). Prefer post-processing for exact phrase swaps.

Rules:
- Output a single JSON object, no markdown fences, no commentary outside JSON.
- Keep strings short. At most 3 query_overrides_add and 3 pattern_overrides_add items.
- query must be normalized lowercase single-line (match how user would type).
- performance_notes: max 400 characters.
- system_suffix: max ~400 characters; concise bullet-style instructions.
- If nothing to change, use empty arrays and empty global fields (omit empty objects or use {}).

Schema (exact keys):
{
  "performance_notes": "...",
  "patch": {
    "prompt": {"system_suffix": ""},
    "global": {
      "replacements": {},
      "blocked_phrases_add": [],
      "blocked_phrases_remove": [],
      "dedupe_sentences": null
    },
    "query_overrides_add": [],
    "pattern_overrides_add": []
  }
}
Use null for dedupe_sentences only if unsure; otherwise true/false as needed. Omit patch.prompt if not needed."""

REFLECTION_CHAT_SYSTEM = """You are running a meta-reflection chat to tune stakeholder behavior.
You must help the user refine tweaks step-by-step and always provide an updated JSON draft.

Response format (strict):
1) A short coaching reply in plain text (max 6 lines).
2) Then a JSON object (same schema as reflection patch payload):
{
  "performance_notes":"...",
  "patch":{
    "prompt":{"system_suffix":""},
    "global":{"replacements":{},"blocked_phrases_add":[],"blocked_phrases_remove":[],"dedupe_sentences":null},
    "query_overrides_add":[],
    "pattern_overrides_add":[]
  }
}
Use patch.prompt.system_suffix for generation-time instructions; use global.* for post-processing.

Rules:
- Keep edits minimal and high impact.
- Keep strings concise.
- If user asks to keep/remove something, update JSON accordingly.
- Output only the coaching text + JSON object. No markdown fences.
"""


def compact_transcript(messages: List[Dict[str, Any]], max_turns: int = 36, max_chars: int = 450) -> str:
    """Turn message list into token-efficient lines for the meta prompt."""
    lines: List[str] = []
    slice_msgs = messages[-max_turns:] if len(messages) > max_turns else messages
    for m in slice_msgs:
        role = str(m.get("role", "")).strip()[:12]
        content = str(m.get("content", "")).replace("\n", " ").strip()
        if len(content) > max_chars:
            content = content[: max_chars - 3] + "..."
        if role and content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines) if lines else "(empty)"


def compact_tweak_snapshot(data: Dict[str, Any]) -> str:
    """Minimal description of current tweak file for the LLM."""
    g = data.get("global") or {}
    reps = g.get("replacements") or {}
    keys = list(reps.keys())[:20]
    blocked = (g.get("blocked_phrases") or [])[:15]
    qo = data.get("query_overrides") or []
    q_sample = []
    for r in qo[-5:]:
        if isinstance(r, dict) and r.get("query"):
            q_sample.append(str(r["query"])[:80])

    po = data.get("pattern_overrides") or []
    po_meta = []
    for r in po[-5:]:
        if isinstance(r, dict):
            ma = r.get("match_any") or []
            po_meta.append({"match_any": ma[:5] if isinstance(ma, list) else []})

    pr = data.get("prompt") if isinstance(data.get("prompt"), dict) else {}
    suf = str((pr or {}).get("system_suffix") or "").strip()
    snap = {
        "dedupe_sentences": g.get("dedupe_sentences"),
        "replacement_keys_n": len(reps),
        "replacement_keys_sample": keys,
        "blocked_phrases": blocked,
        "query_override_count": len(qo),
        "query_override_queries_sample": q_sample,
        "pattern_override_count": len(po),
        "pattern_overrides_meta_sample": po_meta,
        "feedback_log_len": len(data.get("feedback_log") or []),
        "system_suffix_chars": len(suf),
        "system_suffix_excerpt": suf[:180] + ("..." if len(suf) > 180 else ""),
    }
    return json.dumps(snap, ensure_ascii=False, separators=(",", ":"))


def build_reflection_user_payload(transcript_block: str, tweak_snapshot_json: str) -> str:
    return (
        "CONVERSATION (most recent turns, user=trainer assistant=stakeholder bot):\n"
        f"{transcript_block}\n\n"
        "CURRENT_TWEAK_SUMMARY_JSON:\n"
        f"{tweak_snapshot_json}\n"
    )


def build_reflection_chat_payload(
    transcript_block: str,
    tweak_snapshot_json: str,
    thread_messages: List[Dict[str, Any]],
    user_message: str,
    current_draft: Optional[Dict[str, Any]] = None,
) -> str:
    lines: List[str] = []
    for m in thread_messages[-16:]:
        role = str(m.get("role", "")).strip()[:12]
        content = " ".join(str(m.get("content", "")).split())
        if role and content:
            lines.append(f"{role}: {content[:700]}")
    history = "\n".join(lines) if lines else "(empty)"
    draft_json = json.dumps(current_draft or {}, ensure_ascii=False, separators=(",", ":"))
    return (
        "BASE CONVERSATION TRANSCRIPT:\n"
        f"{transcript_block}\n\n"
        "CURRENT TWEAK SUMMARY:\n"
        f"{tweak_snapshot_json}\n\n"
        "REFLECTION THREAD HISTORY:\n"
        f"{history}\n\n"
        "CURRENT JSON DRAFT (may be empty):\n"
        f"{draft_json}\n\n"
        "NEW USER MESSAGE:\n"
        f"{user_message}\n"
    )


def _find_balanced_object_end(s: str, start: int) -> Optional[int]:
    """Index of the closing ``}`` for a ``{`` at ``start``, or None. Respects JSON string literals."""
    if start >= len(s) or s[start] != "{":
        return None
    depth = 0
    i = start
    in_str = False
    esc = False
    while i < len(s):
        c = s[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            i += 1
            continue
        if c == '"':
            in_str = True
            i += 1
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return None


def _iter_balanced_object_spans(s: str):
    for i, c in enumerate(s):
        if c != "{":
            continue
        end = _find_balanced_object_end(s, i)
        if end is not None:
            yield i, end


def _try_loads_json_object(chunk: str) -> Optional[Dict[str, Any]]:
    try:
        obj = json.loads(chunk)
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def _is_reflection_json_shape(obj: Dict[str, Any]) -> bool:
    """True if this dict is the outer reflection payload, not a nested inner object like ``{{}}``."""
    if not obj:
        return False
    if "patch" in obj:
        return True
    if "performance_notes" in obj:
        return True
    return False


def _repair_trailing_commas(j: str) -> str:
    cur = j
    for _ in range(16):
        nxt = re.sub(r",(\s*[}\]])", r"\1", cur)
        if nxt == cur:
            return cur
        cur = nxt
    return cur


def _reflection_non_json_fallback(
    raw: str,
    draft_fallback: Optional[Dict[str, Any]] = None,
) -> Tuple[str, Dict[str, Any]]:
    """Model returned prose or malformed JSON: surface full text as the assistant note; keep prior draft patch."""
    text = (raw or "").strip()
    if not text:
        text = (
            "The model returned an empty response. Your tweak draft was left unchanged — try a shorter follow-up."
        )
    notes = text
    base = draft_fallback if isinstance(draft_fallback, dict) else {}
    preserved_patch: Dict[str, Any] = {}
    if base:
        norm = normalize_reflection_payload(dict(base))
        p = norm.get("patch")
        if isinstance(p, dict):
            preserved_patch = p
    payload = normalize_reflection_payload({"performance_notes": notes[:450], "patch": preserved_patch})
    return notes, payload


def split_reflection_response_fallback(
    raw: str,
    draft_fallback: Optional[Dict[str, Any]] = None,
) -> Tuple[str, Dict[str, Any]]:
    """Like :func:`split_reflection_response` but never raises: falls back to prose + preserved draft."""
    try:
        return split_reflection_response(raw)
    except ValueError:
        return _reflection_non_json_fallback(raw, draft_fallback)


def split_reflection_response(raw: str) -> Tuple[str, Dict[str, Any]]:
    """Split optional coaching prose from the reflection JSON object; return (notes, normalized payload).

    Tries, in order: fenced markdown block, whole-string JSON, then each balanced ``{...}`` span from
    the end (reflection chat puts JSON after prose). Trailing-comma repair is applied per chunk.
    """
    text = raw.strip()
    if not text:
        raise ValueError("Empty reflection response")

    fenced_inner: Optional[str] = None
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if fence:
        fenced_inner = fence.group(1).strip()

    work_sources: List[str] = []
    if fenced_inner:
        work_sources.append(fenced_inner)
    work_sources.append(text)

    seen_work: set[str] = set()
    for work in work_sources:
        if not work or work in seen_work:
            continue
        seen_work.add(work)

        obj = _try_loads_json_object(work)
        if obj is not None:
            return "", normalize_reflection_payload(obj)
        rep = _repair_trailing_commas(work)
        if rep != work:
            obj = _try_loads_json_object(rep)
            if obj is not None:
                return "", normalize_reflection_payload(obj)

        spans = list(_iter_balanced_object_spans(work))
        best: Optional[Tuple[int, int, Dict[str, Any]]] = None
        for start, end in spans:
            chunk = work[start : end + 1]
            obj = _try_loads_json_object(chunk)
            if obj is None:
                rep = _repair_trailing_commas(chunk)
                if rep != chunk:
                    obj = _try_loads_json_object(rep)
            if obj is None or not _is_reflection_json_shape(obj):
                continue
            if best is None or (end - start) > (best[1] - best[0]):
                best = (start, end, obj)
        if best is not None:
            start, end, obj = best
            return work[:start].strip(), normalize_reflection_payload(obj)

    raise ValueError("No JSON object in reflection response")


def parse_reflection_json(raw: str) -> Dict[str, Any]:
    """Extract and parse JSON object from model output."""
    _, payload = split_reflection_response(raw)
    return payload


def normalize_reflection_payload(obj: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure patch structure exists and cap list sizes for safety."""
    notes = obj.get("performance_notes")
    if notes is not None and not isinstance(notes, str):
        notes = str(notes)
    if isinstance(notes, str) and len(notes) > 450:
        notes = notes[:447] + "..."

    patch = obj.get("patch")
    if patch is None or not isinstance(patch, dict):
        patch = {}

    g = patch.get("global")
    if not isinstance(g, dict):
        g = {}
    reps = g.get("replacements")
    if reps is not None and not isinstance(reps, dict):
        reps = {}
    if isinstance(reps, dict):
        g["replacements"] = {str(k)[:200]: str(v)[:200] for k, v in list(reps.items())[:25]}

    for key in ("blocked_phrases_add", "blocked_phrases_remove"):
        arr = g.get(key)
        if arr is None:
            g[key] = []
        elif not isinstance(arr, list):
            g[key] = []
        else:
            g[key] = [str(x)[:120] for x in arr[:20]]

    if "dedupe_sentences" in g and g["dedupe_sentences"] is not None:
        g["dedupe_sentences"] = bool(g["dedupe_sentences"])

    patch["global"] = g

    q_add = patch.get("query_overrides_add")
    if not isinstance(q_add, list):
        q_add = []
    cleaned_q = []
    for item in q_add[:5]:
        if not isinstance(item, dict):
            continue
        q = item.get("query") or item.get("query_norm")
        resp = item.get("response")
        if q and resp:
            cleaned_q.append({"query": str(q)[:500], "response": str(resp)[:500]})
    patch["query_overrides_add"] = cleaned_q[:3]

    p_add = patch.get("pattern_overrides_add")
    if not isinstance(p_add, list):
        p_add = []
    cleaned_p = []
    for item in p_add[:5]:
        if not isinstance(item, dict):
            continue
        ma = item.get("match_any")
        resp = item.get("response")
        if isinstance(ma, list) and resp:
            cleaned_p.append(
                {
                    "match_any": [str(x)[:80] for x in ma[:8]],
                    "response": str(resp)[:500],
                }
            )
    patch["pattern_overrides_add"] = cleaned_p[:3]

    p_prompt = patch.get("prompt")
    if isinstance(p_prompt, dict) and "system_suffix" in p_prompt:
        ss = p_prompt.get("system_suffix")
        patch["prompt"] = {"system_suffix": str(ss if ss is not None else "")[:800]}

    return {"performance_notes": notes or "", "patch": patch}


def pick_reflection_llm(llm_by_mode: Dict[str, Any]) -> Tuple[str, Any]:
    """Prefer vector LLM, else neo4j, else any available."""
    if llm_by_mode.get("vector"):
        return "vector", llm_by_mode["vector"]
    if llm_by_mode.get("neo4j"):
        return "neo4j", llm_by_mode["neo4j"]
    for name, w in llm_by_mode.items():
        if w is not None:
            return str(name), w
    raise ValueError("No LLM wrapper available for reflection")
