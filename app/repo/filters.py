"""Ingestion exclude rules and quotas."""

from __future__ import annotations

import os
from pathlib import PurePosixPath

EXCLUDED_DIR_NAMES = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
    "coverage",
    "__pycache__",
    ".next",
    ".turbo",
    "vendor",
    "target",
    ".idea",
    ".vscode",
}

EXCLUDED_FILE_NAMES = {
    ".env",
    ".env.local",
    ".env.production",
    "credentials.json",
    "secrets.json",
}

EXCLUDED_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".ico",
    ".pdf",
    ".zip",
    ".gz",
    ".tar",
    ".7z",
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".bin",
    ".wasm",
    ".pyc",
    ".pyo",
    ".class",
    ".o",
    ".a",
    ".lock",
}

EXCLUDED_BASENAME_SUFFIXES = {
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "poetry.lock",
    "Cargo.lock",
}


def should_exclude_path(path: str) -> bool:
    parts = PurePosixPath(path).parts
    if any(part in EXCLUDED_DIR_NAMES for part in parts[:-1]):
        return True
    name = os.path.basename(path)
    if name in EXCLUDED_FILE_NAMES:
        return True
    if name in EXCLUDED_BASENAME_SUFFIXES:
        return True
    lower = name.lower()
    for ext in EXCLUDED_EXTENSIONS:
        if lower.endswith(ext):
            return True
    if lower.startswith(".env"):
        return True
    return False


def guess_language(path: str) -> str | None:
    ext = PurePosixPath(path).suffix.lower()
    return {
        ".py": "python",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".js": "javascript",
        ".jsx": "javascript",
        ".go": "go",
        ".rs": "rust",
        ".java": "java",
        ".kt": "kotlin",
        ".md": "markdown",
        ".yml": "yaml",
        ".yaml": "yaml",
        ".json": "json",
        ".sql": "sql",
        ".css": "css",
        ".html": "html",
    }.get(ext)
