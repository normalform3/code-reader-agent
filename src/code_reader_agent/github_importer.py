"""Import public GitHub repositories into a local read-only analysis cache."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse

from code_reader_agent.models import GitHubImportResult


_GITHUB_NAME_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")


class GitHubImportError(ValueError):
    """Raised when a GitHub import request is invalid."""


class GitHubCloneError(RuntimeError):
    """Raised when a public GitHub repository cannot be cloned."""


class _CommandRunner(Protocol):
    def __call__(self, args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        """Run a command with subprocess-compatible arguments."""


def import_github_repository(
    github_url: str,
    *,
    cache_root: Path | None = None,
    runner: _CommandRunner = subprocess.run,
) -> GitHubImportResult:
    """Clone a public GitHub repository into a local cache and return its path."""

    parsed = parse_github_repository_url(github_url)
    effective_cache_root = cache_root or _default_cache_root()
    target_path = effective_cache_root / f"{parsed.owner}__{parsed.repo}__default"
    normalized_url = f"https://github.com/{parsed.owner}/{parsed.repo}.git"

    warnings: list[str] = []
    reused_cache = target_path.exists() and any(target_path.iterdir())
    if not reused_cache:
        effective_cache_root.mkdir(parents=True, exist_ok=True)
        _clone_repository(normalized_url, target_path, runner)
    else:
        warnings.append("Repository cache already exists; reused local read-only snapshot.")

    return GitHubImportResult(
        project_name=parsed.repo,
        project_path=str(target_path.resolve()),
        github_url=normalized_url,
        repository=f"{parsed.owner}/{parsed.repo}",
        reused_cache=reused_cache,
        warnings=warnings,
    )


class ParsedGitHubRepository:
    """A validated GitHub owner/repository pair."""

    def __init__(self, owner: str, repo: str) -> None:
        self.owner = owner
        self.repo = repo


def parse_github_repository_url(github_url: str) -> ParsedGitHubRepository:
    """Parse and validate a public GitHub repository URL."""

    raw_url = github_url.strip()
    if not raw_url:
        raise GitHubImportError("GitHub URL is required.")

    parsed = urlparse(raw_url)
    if parsed.scheme != "https" or parsed.netloc.lower() != "github.com":
        raise GitHubImportError("Only https://github.com/owner/repo URLs are supported.")

    path_parts = [part for part in parsed.path.strip("/").split("/") if part]
    if len(path_parts) != 2:
        raise GitHubImportError("GitHub URL must point to a repository, for example https://github.com/owner/repo.")

    owner, repo = path_parts
    if repo.endswith(".git"):
        repo = repo[:-4]

    if not _is_safe_github_name(owner) or not _is_safe_github_name(repo):
        raise GitHubImportError("GitHub owner and repository names may only contain letters, numbers, dots, dashes, and underscores.")

    return ParsedGitHubRepository(owner=owner, repo=repo)


def _is_safe_github_name(value: str) -> bool:
    return bool(value and _GITHUB_NAME_PATTERN.fullmatch(value))


def _default_cache_root() -> Path:
    configured_root = os.environ.get("CODEREADER_GITHUB_CACHE_DIR")
    if configured_root:
        return Path(configured_root).expanduser()
    return Path.cwd() / ".codereader" / "repos"


def _clone_repository(clone_url: str, target_path: Path, runner: _CommandRunner) -> None:
    command = ["git", "clone", "--depth", "1", clone_url, str(target_path)]
    try:
        runner(command, check=True, capture_output=True, text=True, timeout=120)
    except FileNotFoundError as exc:
        raise GitHubCloneError("git executable was not found. Install git before importing GitHub repositories.") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        message = "GitHub repository could not be cloned. Confirm it exists and is public."
        if detail:
            message = f"{message} git output: {detail}"
        raise GitHubCloneError(message) from exc
    except subprocess.TimeoutExpired as exc:
        raise GitHubCloneError("GitHub repository clone timed out.") from exc
