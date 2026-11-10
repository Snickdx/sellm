"""Build a frozen repository index pinned to a commit SHA."""

from __future__ import annotations

import re
from typing import Any

from app.course.settings import Settings
from app.course.providers.github import RepoRef, RepositoryProvider, TreeEntry
from app.course.repo.filters import guess_language, should_exclude_path

PY_DEF_RE = re.compile(r"^(?P<indent>\s*)(async\s+)?def\s+(?P<name>[A-Za-z_]\w*)\s*\(")
PY_CLASS_RE = re.compile(r"^(?P<indent>\s*)class\s+(?P<name>[A-Za-z_]\w*)\s*[\(:]")
JS_FN_RE = re.compile(
    r"^\s*(export\s+)?(async\s+)?function\s+(?P<name>[A-Za-z_]\w*)\s*\("
)
JS_CLASS_RE = re.compile(r"^\s*(export\s+)?class\s+(?P<name>[A-Za-z_]\w*)\b")
JS_CONST_FN_RE = re.compile(
    r"^\s*(export\s+)?(const|let|var)\s+(?P<name>[A-Za-z_]\w*)\s*=\s*(async\s*)?\("
)


def _extract_symbols(path: str, text: str, language: str | None) -> list[dict[str, Any]]:
    symbols: list[dict[str, Any]] = []
    lines = text.splitlines()
    if language == "python":
        for i, line in enumerate(lines, start=1):
            m = PY_CLASS_RE.match(line) or PY_DEF_RE.match(line)
            if m:
                symbols.append(
                    {
                        "name": m.group("name"),
                        "kind": "class" if line.lstrip().startswith("class") else "function",
                        "path": path,
                        "line_start": i,
                        "line_end": i,
                    }
                )
    elif language in {"javascript", "typescript"}:
        for i, line in enumerate(lines, start=1):
            m = JS_CLASS_RE.match(line) or JS_FN_RE.match(line) or JS_CONST_FN_RE.match(line)
            if m:
                kind = "class" if "class " in line else "function"
                symbols.append(
                    {
                        "name": m.group("name"),
                        "kind": kind,
                        "path": path,
                        "line_start": i,
                        "line_end": i,
                    }
                )
    return symbols


def _is_test_path(path: str) -> bool:
    lower = path.lower()
    name = lower.rsplit("/", 1)[-1]
    return (
        "/tests/" in f"/{lower}"
        or "/__tests__/" in f"/{lower}"
        or name.startswith("test_")
        or name.endswith("_test.py")
        or name.endswith(".test.ts")
        or name.endswith(".test.tsx")
        or name.endswith(".spec.ts")
        or name.endswith(".spec.js")
    )


def _is_doc_path(path: str) -> bool:
    lower = path.lower()
    return lower.endswith(".md") or lower.startswith("docs/") or lower in {"readme.md", "readme"}


def build_index(
    *,
    provider: RepositoryProvider,
    ref: RepoRef,
    sha: str,
    settings: Settings,
) -> tuple[dict[str, Any], dict[str, Any]]:
    commit_meta = provider.verify_commit(ref, sha)
    resolved_sha = commit_meta.get("sha") or sha
    tree = provider.list_tree(ref, resolved_sha)

    files: list[dict[str, Any]] = []
    symbols: list[dict[str, Any]] = []
    tests: list[dict[str, Any]] = []
    docs: list[dict[str, Any]] = []
    contents: dict[str, str] = {}
    skipped: list[dict[str, Any]] = []
    total_bytes = 0

    candidates = [e for e in tree if e.type == "blob" and not should_exclude_path(e.path)]
    candidates.sort(key=lambda e: e.path)

    for entry in candidates:
        if len(files) >= settings.repo_max_files:
            skipped.append({"path": entry.path, "reason": "max_files"})
            continue
        if entry.size > settings.repo_max_file_bytes:
            skipped.append({"path": entry.path, "reason": "max_file_bytes", "size": entry.size})
            continue
        if total_bytes + entry.size > settings.repo_max_total_bytes:
            skipped.append({"path": entry.path, "reason": "max_total_bytes"})
            continue

        try:
            text = provider.get_file_text(ref, resolved_sha, entry.path)
        except Exception as exc:  # noqa: BLE001 — collect and continue
            skipped.append({"path": entry.path, "reason": f"read_error:{exc}"})
            continue

        # Reject likely binary / null-heavy payloads
        if "\x00" in text[:2048]:
            skipped.append({"path": entry.path, "reason": "binary"})
            continue

        encoded_size = len(text.encode("utf-8", errors="replace"))
        if encoded_size > settings.repo_max_file_bytes:
            skipped.append({"path": entry.path, "reason": "decoded_too_large", "size": encoded_size})
            continue

        language = guess_language(entry.path)
        line_count = text.count("\n") + (1 if text and not text.endswith("\n") else 0)
        file_rec = {
            "path": entry.path,
            "size": encoded_size,
            "language": language,
            "blob_sha": entry.sha,
            "line_count": line_count,
        }
        files.append(file_rec)
        contents[entry.path] = text
        total_bytes += encoded_size

        file_symbols = _extract_symbols(entry.path, text, language)
        symbols.extend(file_symbols)
        if _is_test_path(entry.path):
            tests.append({**file_rec, "symbol_count": len(file_symbols)})
        if _is_doc_path(entry.path):
            docs.append(file_rec)

    prs: list[dict[str, Any]] = []
    try:
        prs = provider.list_prs(ref, resolved_sha)
    except Exception:  # noqa: BLE001
        prs = []

    index = {
        "commit_sha": resolved_sha,
        "owner": ref.owner,
        "repo": ref.repo,
        "source": ref.source,
        "files": files,
        "symbols": symbols,
        "tests": tests,
        "docs": docs,
        "prs": prs,
        "contents": contents,
        "skipped": skipped,
        "stats": {
            "file_count": len(files),
            "symbol_count": len(symbols),
            "test_file_count": len(tests),
            "doc_file_count": len(docs),
            "skipped_count": len(skipped),
            "total_bytes": total_bytes,
        },
    }
    summary = build_summary(index, commit_meta=commit_meta)
    return index, summary


def build_summary(index: dict[str, Any], *, commit_meta: dict[str, Any]) -> dict[str, Any]:
    files = index.get("files") or []
    symbols = index.get("symbols") or []
    tests = index.get("tests") or []
    docs = index.get("docs") or []
    sha = index.get("commit_sha")

    citations: list[dict[str, Any]] = []
    for sym in symbols[:8]:
        citations.append(
            {
                "kind": "symbol",
                "name": sym["name"],
                "path": sym["path"],
                "line_range": [sym["line_start"], sym["line_end"]],
                "sha": sha,
            }
        )
    for test in tests[:5]:
        citations.append(
            {
                "kind": "test_file",
                "path": test["path"],
                "line_range": [1, min(20, test.get("line_count") or 1)],
                "sha": sha,
            }
        )

    languages: dict[str, int] = {}
    for f in files:
        lang = f.get("language") or "other"
        languages[lang] = languages.get(lang, 0) + 1

    return {
        "commit_sha": sha,
        "commit_message": commit_meta.get("message"),
        "html_url": commit_meta.get("html_url"),
        "languages": languages,
        "highlights": {
            "top_symbols": [s["name"] for s in symbols[:12]],
            "test_files": [t["path"] for t in tests[:12]],
            "doc_files": [d["path"] for d in docs[:12]],
        },
        "citations": citations,
        "stats": index.get("stats"),
        "uncertainty": []
        if symbols
        else ["Limited symbol extraction — prefer file-level questions or mark hypothetical."],
    }


def tree_preview(entries: list[TreeEntry], limit: int = 50) -> list[str]:
    return [e.path for e in entries[:limit]]
