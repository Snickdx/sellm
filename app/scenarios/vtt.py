"""Deterministic WebVTT parser with cue/source/speaker preservation."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

TIMESTAMP_RE = re.compile(
    r"^(?P<start>\d{2}:\d{2}:\d{2}\.\d{3})\s+-->\s+(?P<end>\d{2}:\d{2}:\d{2}\.\d{3})"
    r"(?:\s+(?P<settings>.+))?$"
)
NOTE_RE = re.compile(r"^NOTE(?:\s|$)")
STYLE_RE = re.compile(r"^STYLE\b")
REGION_RE = re.compile(r"^REGION\b")
SPEAKER_TAG_RE = re.compile(r"^<v(?:\s+([^>]+))?>(.*)$", re.DOTALL)
SPEAKER_PREFIX_RE = re.compile(r"^([A-Za-z][A-Za-z0-9 _./-]{0,40}):\s+(.*)$", re.DOTALL)


@dataclass(frozen=True)
class ParsedCue:
    cue_id: str
    start: str
    end: str
    text: str
    raw_text: str
    speaker: str | None
    speaker_confidence: str  # high | medium | low | none
    source_file: str
    settings: str | None = None
    overlapping: bool = False


def _strip_bom(text: str) -> str:
    return text.lstrip("\ufeff")


def _normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _split_blocks(body: str) -> list[str]:
    blocks: list[str] = []
    current: list[str] = []
    for line in body.split("\n"):
        if line.strip() == "":
            if current:
                blocks.append("\n".join(current))
                current = []
            continue
        current.append(line)
    if current:
        blocks.append("\n".join(current))
    return blocks


def _extract_speaker(text: str) -> tuple[str, str | None, str]:
    """Return (clean_text, speaker, confidence)."""
    stripped = text.strip()
    tag = SPEAKER_TAG_RE.match(stripped)
    if tag:
        speaker = (tag.group(1) or "").strip() or None
        body = (tag.group(2) or "").strip()
        if speaker:
            return body, speaker, "high"
        return body, None, "low"

    prefix = SPEAKER_PREFIX_RE.match(stripped)
    if prefix:
        return prefix.group(2).strip(), prefix.group(1).strip(), "medium"

    return stripped, None, "none"


def _times_overlap(a_start: str, a_end: str, b_start: str, b_end: str) -> bool:
    return a_start < b_end and b_start < a_end


def parse_vtt(content: str, *, source_file: str = "unknown.vtt") -> list[ParsedCue]:
    text = _normalize_newlines(_strip_bom(content))
    lines = text.split("\n")
    if not lines or not lines[0].strip().startswith("WEBVTT"):
        raise ValueError(f"{source_file}: missing WEBVTT header")

    # Drop header line and optional header metadata until blank
    idx = 1
    while idx < len(lines) and lines[idx].strip() != "":
        idx += 1
    while idx < len(lines) and lines[idx].strip() == "":
        idx += 1

    body = "\n".join(lines[idx:])
    blocks = _split_blocks(body)
    cues: list[ParsedCue] = []
    auto_id = 0

    for block in blocks:
        block_lines = block.split("\n")
        first = block_lines[0].strip()
        if NOTE_RE.match(first) or STYLE_RE.match(first) or REGION_RE.match(first):
            continue

        cue_id: str | None = None
        ts_line_idx = 0
        ts_match = TIMESTAMP_RE.match(first)
        if ts_match is None:
            if len(block_lines) < 2:
                continue
            cue_id = first
            ts_match = TIMESTAMP_RE.match(block_lines[1].strip())
            if ts_match is None:
                continue
            ts_line_idx = 1

        payload_lines = block_lines[ts_line_idx + 1 :]
        if not payload_lines:
            continue

        raw_text = "\n".join(payload_lines).strip()
        clean_text, speaker, confidence = _extract_speaker(raw_text)
        auto_id += 1
        resolved_id = cue_id if cue_id else f"cue-{auto_id:04d}"

        cues.append(
            ParsedCue(
                cue_id=resolved_id,
                start=ts_match.group("start"),
                end=ts_match.group("end"),
                text=clean_text,
                raw_text=raw_text,
                speaker=speaker,
                speaker_confidence=confidence,
                source_file=source_file,
                settings=ts_match.group("settings"),
            )
        )

    # Flag overlaps without inventing speakers
    marked: list[ParsedCue] = []
    for i, cue in enumerate(cues):
        overlapping = any(
            i != j and _times_overlap(cue.start, cue.end, other.start, other.end)
            for j, other in enumerate(cues)
        )
        marked.append(
            ParsedCue(
                cue_id=cue.cue_id,
                start=cue.start,
                end=cue.end,
                text=cue.text,
                raw_text=cue.raw_text,
                speaker=cue.speaker,
                speaker_confidence=cue.speaker_confidence,
                source_file=cue.source_file,
                settings=cue.settings,
                overlapping=overlapping,
            )
        )
    return marked


def parse_vtt_file(path: Path) -> list[ParsedCue]:
    return parse_vtt(path.read_text(encoding="utf-8"), source_file=path.name)


def cues_to_jsonl(cues: list[ParsedCue]) -> str:
    return "\n".join(json.dumps(asdict(c), ensure_ascii=False) for c in cues) + ("\n" if cues else "")
