"""Classify queries for hybrid handoff: Neo4j graph vs Chroma semantic retrieval."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Tuple


class QueryRoute(str, Enum):
    NEO4J = "neo4j"
    CHROMA = "chroma"
    BLEND = "blend"


@dataclass(frozen=True)
class RouteDecision:
    route: QueryRoute
    neo4j_score: float
    chroma_score: float
    reasons: List[str]


# Graph / relationship / structured traversal signals
_NEO4J_PATTERNS: List[Tuple[str, float]] = [
    (r"\b(related|relationship|connected|connection|link|linked)\b", 0.35),
    (r"\b(depends? on|dependency|dependencies)\b", 0.4),
    (r"\b(between|path|traverse|upstream|downstream)\b", 0.3),
    (r"\b(who (owns|reports|depends)|stakeholder of|owned by)\b", 0.35),
    (r"\b(timeline|milestone|sequence|order of|before|after)\b", 0.25),
    (r"\b(associated with|parent|child|neighbor)\b", 0.3),
    (r"\b(node id|node_id|id [A-Za-z0-9_-]+)\b", 0.35),
    (r"\b(how (is|are) .+ (connected|related))\b", 0.4),
    (r"\b(which .+ (depend|relate|connect))\b", 0.35),
    (r"\b(graph|cypher|traverse)\b", 0.45),
]

# Semantic / exploratory / narrative signals
_CHROMA_PATTERNS: List[Tuple[str, float]] = [
    (r"\b(tell me about|describe|explain|walk me through)\b", 0.35),
    (r"\b(what are your|how do you feel|concern|worried|think about)\b", 0.3),
    (r"\b(overview|in general|broadly|high level)\b", 0.25),
    (r"\b(goals?|objectives?|vision|purpose)\b", 0.2),
    (r"\b(features?|functionality|capabilities)\b", 0.2),
    (r"\b(requirements?|needs?|expectations?)\b", 0.15),
    (r"\b(budget|cost|money|price)\b", 0.15),
    (r"\b(risks?|issues?|problems?)\b", 0.15),
    (r"\b(stakeholders?|clients?|users?)\b", 0.15),
]

_SHEET_NEO4J_HINTS = {
    "timeline",
    "milestone",
    "task",
    "relationship",
    "project",
    "line_item",
}

_SHEET_CHROMA_HINTS = {
    "goal",
    "feature",
    "requirement",
    "risk",
    "budget",
    "stakeholder",
    "client",
    "qual_scenario",
}


def _score_patterns(query: str, patterns: List[Tuple[str, float]]) -> Tuple[float, List[str]]:
    q = query.lower()
    total = 0.0
    hits: List[str] = []
    for pattern, weight in patterns:
        if re.search(pattern, q, re.IGNORECASE):
            total += weight
            hits.append(pattern)
    return total, hits


def _sheet_bias(query: str) -> Tuple[float, float, List[str]]:
    q = query.lower()
    neo = 0.0
    chroma = 0.0
    reasons: List[str] = []
    for hint in _SHEET_NEO4J_HINTS:
        if hint.replace("_", " ") in q or hint in q:
            neo += 0.12
            reasons.append(f"sheet-hint-neo4j:{hint}")
    for hint in _SHEET_CHROMA_HINTS:
        if hint.replace("_", " ") in q or hint in q:
            chroma += 0.1
            reasons.append(f"sheet-hint-chroma:{hint}")
    return neo, chroma, reasons


def route_query(query: str, margin: float = 0.15) -> RouteDecision:
    """
    Pick retrieval backend for hybrid mode.

    - neo4j: relationship / traversal / structured graph questions
    - chroma: semantic similarity / broad exploratory questions
    - blend: close scores — use both with weighted merge
    """
    neo_score, neo_hits = _score_patterns(query, _NEO4J_PATTERNS)
    chroma_score, chroma_hits = _score_patterns(query, _CHROMA_PATTERNS)
    sheet_neo, sheet_chroma, sheet_reasons = _sheet_bias(query)
    neo_score += sheet_neo
    chroma_score += sheet_chroma

    reasons: List[str] = []
    if neo_hits:
        reasons.append(f"neo4j-patterns:{len(neo_hits)}")
    if chroma_hits:
        reasons.append(f"chroma-patterns:{len(chroma_hits)}")
    reasons.extend(sheet_reasons)

    # Short questions without strong signals default slightly toward Chroma (semantic RAG)
    word_count = len(query.split())
    if word_count <= 6 and neo_score < 0.25 and chroma_score < 0.2:
        chroma_score += 0.1
        reasons.append("short-query-chroma-default")

    if neo_score >= chroma_score + margin:
        route = QueryRoute.NEO4J
        reasons.append("winner:neo4j")
    elif chroma_score >= neo_score + margin:
        route = QueryRoute.CHROMA
        reasons.append("winner:chroma")
    else:
        route = QueryRoute.BLEND
        reasons.append("winner:blend")

    return RouteDecision(
        route=route,
        neo4j_score=round(neo_score, 3),
        chroma_score=round(chroma_score, 3),
        reasons=reasons,
    )


def route_to_dict(decision: RouteDecision) -> Dict[str, object]:
    return {
        "route": decision.route.value,
        "neo4j_score": decision.neo4j_score,
        "chroma_score": decision.chroma_score,
        "reasons": decision.reasons,
    }
