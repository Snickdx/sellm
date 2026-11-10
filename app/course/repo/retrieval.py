"""Read-only retrieval over a frozen repository index."""

from __future__ import annotations

from typing import Any


def _require_ready(index: dict[str, Any] | None) -> dict[str, Any]:
    if not index:
        raise ValueError("Repository index is empty")
    return index


def search_code(index: dict[str, Any] | None, query: str, *, limit: int = 20) -> list[dict[str, Any]]:
    idx = _require_ready(index)
    q = query.strip().lower()
    if not q:
        return []
    hits: list[dict[str, Any]] = []
    contents: dict[str, str] = idx.get("contents") or {}
    sha = idx.get("commit_sha")
    for path, text in contents.items():
        lines = text.splitlines()
        for i, line in enumerate(lines, start=1):
            if q in line.lower():
                start = max(1, i - 2)
                end = min(len(lines), i + 2)
                excerpt = "\n".join(f"{n}: {lines[n - 1]}" for n in range(start, end + 1))
                hits.append(
                    {
                        "path": path,
                        "line": i,
                        "line_range": [start, end],
                        "sha": sha,
                        "excerpt": excerpt,
                    }
                )
                if len(hits) >= limit:
                    return hits
    return hits


def get_file(
    index: dict[str, Any] | None,
    path: str,
    *,
    start_line: int | None = None,
    end_line: int | None = None,
) -> dict[str, Any]:
    idx = _require_ready(index)
    contents: dict[str, str] = idx.get("contents") or {}
    if path not in contents:
        raise FileNotFoundError(path)
    text = contents[path]
    lines = text.splitlines()
    start = start_line or 1
    end = end_line or len(lines)
    start = max(1, start)
    end = min(len(lines), end)
    numbered = "\n".join(f"{n}: {lines[n - 1]}" for n in range(start, end + 1))
    return {
        "path": path,
        "sha": idx.get("commit_sha"),
        "line_range": [start, end],
        "content": numbered,
        "line_count": len(lines),
    }


def get_symbol(index: dict[str, Any] | None, name: str) -> list[dict[str, Any]]:
    idx = _require_ready(index)
    needle = name.strip()
    results = []
    contents: dict[str, str] = idx.get("contents") or {}
    for sym in idx.get("symbols") or []:
        if sym.get("name") == needle or needle.lower() in str(sym.get("name", "")).lower():
            path = sym["path"]
            text = contents.get(path, "")
            line_count = text.count("\n") + (1 if text else 0)
            start = sym.get("line_start", 1)
            end = min(start + 30, line_count or start)
            snippet = get_file(idx, path, start_line=start, end_line=end)
            results.append({**sym, "sha": idx.get("commit_sha"), "excerpt": snippet["content"]})
    return results


def get_tests(index: dict[str, Any] | None) -> list[dict[str, Any]]:
    idx = _require_ready(index)
    out = []
    for test in idx.get("tests") or []:
        path = test["path"]
        try:
            preview = get_file(idx, path, start_line=1, end_line=min(40, test.get("line_count") or 40))
            out.append({**test, "sha": idx.get("commit_sha"), "excerpt": preview["content"]})
        except FileNotFoundError:
            out.append({**test, "sha": idx.get("commit_sha")})
    return out


def get_pr(index: dict[str, Any] | None, number: int | None = None) -> list[dict[str, Any]]:
    idx = _require_ready(index)
    prs = list(idx.get("prs") or [])
    if number is None:
        return prs
    return [p for p in prs if p.get("number") == number]


def strip_contents_for_api(index: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return index metadata without full file bodies (for status endpoints)."""
    if not index:
        return None
    clone = {k: v for k, v in index.items() if k != "contents"}
    return clone
