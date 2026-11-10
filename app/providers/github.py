"""Read-only repository providers (GitHub API + local fixtures)."""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse

import httpx

from app.settings import Settings

GITHUB_URL_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?github\.com/(?P<owner>[^/]+)/(?P<repo>[^/#?]+?)(?:\.git)?/?$",
    re.I,
)
FIXTURE_URL_RE = re.compile(r"^fixture://(?P<name>[a-zA-Z0-9._-]+)$")


@dataclass(frozen=True)
class RepoRef:
    owner: str
    repo: str
    source: str  # github | fixture
    display_url: str


@dataclass(frozen=True)
class TreeEntry:
    path: str
    size: int
    sha: str
    type: str  # blob | tree


class RepositoryProvider(Protocol):
    def resolve_head(self, ref: RepoRef, branch: str | None = None) -> dict: ...

    def verify_commit(self, ref: RepoRef, sha: str) -> dict: ...

    def list_tree(self, ref: RepoRef, sha: str) -> list[TreeEntry]: ...

    def get_file_text(self, ref: RepoRef, sha: str, path: str) -> str: ...

    def list_prs(self, ref: RepoRef, sha: str) -> list[dict]: ...


def parse_repo_url(url: str) -> RepoRef:
    raw = url.strip()
    fixture = FIXTURE_URL_RE.match(raw)
    if fixture:
        name = fixture.group("name")
        return RepoRef(owner="fixture", repo=name, source="fixture", display_url=raw)

    match = GITHUB_URL_RE.match(raw)
    if match:
        return RepoRef(
            owner=match.group("owner"),
            repo=match.group("repo"),
            source="github",
            display_url=f"https://github.com/{match.group('owner')}/{match.group('repo')}",
        )

    # Allow owner/repo shorthand
    if re.match(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", raw):
        owner, repo = raw.split("/", 1)
        return RepoRef(
            owner=owner,
            repo=repo.removesuffix(".git"),
            source="github",
            display_url=f"https://github.com/{owner}/{repo.removesuffix('.git')}",
        )

    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    if parsed.netloc.endswith("github.com"):
        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) >= 2:
            return RepoRef(
                owner=parts[0],
                repo=parts[1].removesuffix(".git"),
                source="github",
                display_url=f"https://github.com/{parts[0]}/{parts[1].removesuffix('.git')}",
            )
    raise ValueError(f"Unrecognized repository URL: {url}")


class GitHubRepositoryProvider:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _base_headers(self) -> dict[str, str]:
        return {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "sellm-examiner",
        }

    def _headers(self, *, use_token: bool = True) -> dict[str, str]:
        headers = self._base_headers()
        if use_token and self.settings.github_token:
            headers["Authorization"] = f"Bearer {self.settings.github_token}"
        return headers

    def _assert_repo_policy(self, ref: RepoRef) -> None:
        allowed = [o.lower() for o in (self.settings.github_allowed_orgs or [])]
        if allowed and ref.owner.lower() not in allowed:
            raise PermissionError(
                f"Repository owner '{ref.owner}' is not in GITHUB_ALLOWED_ORGS"
            )

    def _ensure_accessible(self, client: httpx.Client, ref: RepoRef) -> dict:
        """Enforce public-only / allowlist so a shared PAT cannot leak private repos."""
        self._assert_repo_policy(ref)
        repo_url = f"{self.settings.github_api_base}/repos/{ref.owner}/{ref.repo}"

        if self.settings.github_public_only:
            # Probe without the server token so private repos the PAT can read stay opaque.
            # Use a token-free client for the visibility check.
            with httpx.Client(timeout=30.0, headers=self._headers(use_token=False)) as anon_client:
                repo_resp = anon_client.get(repo_url)
            if repo_resp.status_code == 404:
                raise FileNotFoundError("Repository not found or not public")
            if repo_resp.status_code == 401:
                raise PermissionError("GitHub authentication failed")
            if repo_resp.status_code == 403:
                raise PermissionError("GitHub access forbidden / rate limited")
            repo_resp.raise_for_status()
            meta = repo_resp.json()
            if bool(meta.get("private")):
                raise PermissionError("Only public repositories are allowed")
            return meta

        repo_resp = client.get(repo_url)
        if repo_resp.status_code == 404:
            raise FileNotFoundError("Repository not found (or private without token)")
        if repo_resp.status_code == 401:
            raise PermissionError("GitHub authentication failed")
        if repo_resp.status_code == 403:
            raise PermissionError("GitHub access forbidden / rate limited")
        repo_resp.raise_for_status()
        return repo_resp.json()

    def resolve_head(self, ref: RepoRef, branch: str | None = None) -> dict:
        """Resolve default-branch (or given branch) tip — students do not enter a SHA."""
        # Token OK after public-only visibility check (rate limits on public repos).
        with httpx.Client(timeout=30.0, headers=self._headers()) as client:
            meta = self._ensure_accessible(client, ref)
            branch_name = (branch or "").strip()
            if not branch_name:
                branch_name = str(meta.get("default_branch") or "main")
            return self.verify_commit(ref, branch_name)

    def verify_commit(self, ref: RepoRef, sha: str) -> dict:
        self._assert_repo_policy(ref)
        url = f"{self.settings.github_api_base}/repos/{ref.owner}/{ref.repo}/commits/{sha}"
        with httpx.Client(timeout=30.0, headers=self._headers()) as client:
            if self.settings.github_public_only:
                self._ensure_accessible(client, ref)
            response = client.get(url)
            if response.status_code == 404:
                raise FileNotFoundError("Commit or repository not found (or private without token)")
            if response.status_code == 401:
                raise PermissionError("GitHub authentication failed")
            if response.status_code == 403:
                raise PermissionError("GitHub access forbidden / rate limited")
            response.raise_for_status()
            data = response.json()
        return {
            "sha": data.get("sha") or sha,
            "message": (data.get("commit") or {}).get("message"),
            "html_url": data.get("html_url"),
        }

    def list_tree(self, ref: RepoRef, sha: str) -> list[TreeEntry]:
        url = f"{self.settings.github_api_base}/repos/{ref.owner}/{ref.repo}/git/trees/{sha}"
        with httpx.Client(timeout=60.0, headers=self._headers()) as client:
            response = client.get(url, params={"recursive": "1"})
            if response.status_code == 404:
                raise FileNotFoundError("Tree not found for commit")
            response.raise_for_status()
            data = response.json()
        entries: list[TreeEntry] = []
        for item in data.get("tree") or []:
            if item.get("type") != "blob":
                continue
            entries.append(
                TreeEntry(
                    path=item["path"],
                    size=int(item.get("size") or 0),
                    sha=item.get("sha") or "",
                    type="blob",
                )
            )
        return entries

    def get_file_text(self, ref: RepoRef, sha: str, path: str) -> str:
        url = f"{self.settings.github_api_base}/repos/{ref.owner}/{ref.repo}/contents/{path}"
        with httpx.Client(timeout=60.0, headers=self._headers()) as client:
            response = client.get(url, params={"ref": sha})
            if response.status_code == 404:
                raise FileNotFoundError(path)
            response.raise_for_status()
            data = response.json()
        if data.get("encoding") == "base64" and data.get("content"):
            raw = base64.b64decode(data["content"])
            return raw.decode("utf-8", errors="replace")
        if isinstance(data.get("content"), str):
            return data["content"]
        raise ValueError(f"Unsupported content payload for {path}")

    def list_prs(self, ref: RepoRef, sha: str) -> list[dict]:
        # Best-effort: commits listing PRs is expensive; return empty unless token allows search.
        _ = sha
        url = f"{self.settings.github_api_base}/repos/{ref.owner}/{ref.repo}/pulls"
        with httpx.Client(timeout=30.0, headers=self._headers()) as client:
            response = client.get(url, params={"state": "all", "per_page": 10})
            if response.status_code >= 400:
                return []
            rows = response.json()
        return [
            {
                "number": row.get("number"),
                "title": row.get("title"),
                "state": row.get("state"),
                "html_url": row.get("html_url"),
            }
            for row in rows
        ]


class FixtureRepositoryProvider:
    """Offline provider for tests and demos: fixture://<name> mapped to a local folder."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def _repo_dir(self, ref: RepoRef) -> Path:
        path = self.root / ref.repo
        if not path.is_dir():
            raise FileNotFoundError(f"Fixture repo not found: {ref.repo}")
        return path

    def resolve_head(self, ref: RepoRef, branch: str | None = None) -> dict:
        _ = branch
        pinned = (self._repo_dir(ref) / ".fixture-sha").read_text(encoding="utf-8").strip()
        return {"sha": pinned, "message": "fixture commit", "html_url": ref.display_url, "branch": "main"}

    def verify_commit(self, ref: RepoRef, sha: str) -> dict:
        repo_dir = self._repo_dir(ref)
        pinned = (repo_dir / ".fixture-sha").read_text(encoding="utf-8").strip()
        if sha in {"HEAD", "head", "main", "master"}:
            return self.resolve_head(ref)
        if sha != pinned and not sha.startswith(pinned[:7]):
            raise FileNotFoundError(f"Fixture SHA mismatch: expected {pinned}")
        return {"sha": pinned, "message": "fixture commit", "html_url": ref.display_url}

    def list_tree(self, ref: RepoRef, sha: str) -> list[TreeEntry]:
        self.verify_commit(ref, sha)
        repo_dir = self._repo_dir(ref)
        entries: list[TreeEntry] = []
        for path in sorted(repo_dir.rglob("*")):
            if path.is_dir():
                continue
            rel = path.relative_to(repo_dir).as_posix()
            if rel == ".fixture-sha":
                continue
            data = path.read_bytes()
            entries.append(TreeEntry(path=rel, size=len(data), sha=f"fixture-{rel}", type="blob"))
        return entries

    def get_file_text(self, ref: RepoRef, sha: str, path: str) -> str:
        self.verify_commit(ref, sha)
        repo_dir = self._repo_dir(ref).resolve()
        file_path = (repo_dir / path).resolve()
        try:
            file_path.relative_to(repo_dir)
        except ValueError as exc:
            raise FileNotFoundError(path) from exc
        if not file_path.is_file():
            raise FileNotFoundError(path)
        return file_path.read_text(encoding="utf-8", errors="replace")

    def list_prs(self, ref: RepoRef, sha: str) -> list[dict]:
        _ = (ref, sha)
        return [
            {
                "number": 1,
                "title": "Fixture PR: add booking service",
                "state": "closed",
                "html_url": "fixture://demo/pull/1",
            }
        ]


def default_fixture_root(settings: Settings) -> Path:
    return settings.fixture_root


def get_repository_provider(settings: Settings, ref: RepoRef) -> RepositoryProvider:
    if ref.source == "fixture":
        return FixtureRepositoryProvider(default_fixture_root(settings))
    return GitHubRepositoryProvider(settings)
