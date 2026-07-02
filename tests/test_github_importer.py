from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from code_reader_agent.github_importer import (
    GitHubCloneError,
    GitHubImportError,
    import_github_repository,
    parse_github_repository_url,
)


def test_parse_github_repository_url_accepts_https_repo_url() -> None:
    parsed = parse_github_repository_url("https://github.com/openai/codex")

    assert parsed.owner == "openai"
    assert parsed.repo == "codex"


def test_parse_github_repository_url_accepts_dot_git_suffix() -> None:
    parsed = parse_github_repository_url("https://github.com/openai/codex.git")

    assert parsed.owner == "openai"
    assert parsed.repo == "codex"


def test_parse_github_repository_url_rejects_invalid_host() -> None:
    with pytest.raises(GitHubImportError, match="Only https://github.com"):
        parse_github_repository_url("https://example.com/openai/codex")


def test_parse_github_repository_url_rejects_empty_url() -> None:
    with pytest.raises(GitHubImportError, match="required"):
        parse_github_repository_url(" ")


def test_import_github_repository_clones_with_argument_list(tmp_path: Path) -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_runner(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    result = import_github_repository("https://github.com/openai/codex.git", cache_root=tmp_path, runner=fake_runner)

    expected_target = tmp_path / "openai__codex__default"
    assert result.project_name == "codex"
    assert result.repository == "openai/codex"
    assert result.project_path == str(expected_target.resolve())
    assert result.reused_cache is False
    assert calls == [
        (
            ["git", "clone", "--depth", "1", "https://github.com/openai/codex.git", str(expected_target)],
            {"check": True, "capture_output": True, "text": True, "timeout": 120},
        )
    ]


def test_import_github_repository_reuses_existing_cache(tmp_path: Path) -> None:
    cached_repo = tmp_path / "openai__codex__default"
    cached_repo.mkdir()
    (cached_repo / "README.md").write_text("# cached\n", encoding="utf-8")

    def fail_runner(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise AssertionError("clone should not run when cache exists")

    result = import_github_repository("https://github.com/openai/codex", cache_root=tmp_path, runner=fail_runner)

    assert result.reused_cache is True
    assert result.project_path == str(cached_repo.resolve())
    assert result.warnings == ["Repository cache already exists; reused local read-only snapshot."]


def test_import_github_repository_maps_clone_failure(tmp_path: Path) -> None:
    def fake_runner(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.CalledProcessError(returncode=128, cmd=args, stderr="repository not found")

    with pytest.raises(GitHubCloneError, match="repository not found"):
        import_github_repository("https://github.com/openai/missing", cache_root=tmp_path, runner=fake_runner)
