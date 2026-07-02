"""Safe read-only tools for local project inspection."""

from __future__ import annotations

import fnmatch
import shutil
import subprocess
from pathlib import Path

from code_reader_agent.models import ReadFileResult, SearchCodeMatch, SearchCodeResult
from code_reader_agent.scanner import IGNORED_DIRECTORIES, ProjectScanError


MAX_READ_CHARS = 12_000
MAX_SEARCH_MATCHES = 50
SENSITIVE_FILE_NAMES = {
    ".env",
    ".env.local",
    ".env.development",
    ".env.production",
    ".npmrc",
    ".pypirc",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
}
SENSITIVE_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".crt", ".cer")


class ReadOnlyToolError(ValueError):
    """Raised when a read-only tool request is invalid or unsafe."""


def read_file(project_path: str | Path, relative_path: str, line_range: tuple[int, int] | None = None) -> ReadFileResult:
    """Read a project file safely without leaving the project root."""

    root, target = _resolve_project_file(project_path, relative_path)
    _ensure_not_sensitive(target)

    try:
        text = target.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise ReadOnlyToolError(f"Could not read file: {relative_path}") from exc

    lines = text.splitlines()
    total_lines = len(lines)
    start_line, end_line = _normalize_line_range(line_range, total_lines)
    selected_lines = lines[start_line - 1 : end_line]
    content = "\n".join(selected_lines)
    warnings: list[str] = []
    truncated = False

    if len(content) > MAX_READ_CHARS:
        content = content[:MAX_READ_CHARS]
        truncated = True
        warnings.append(f"File excerpt truncated to {MAX_READ_CHARS} characters.")

    return ReadFileResult(
        path=target.relative_to(root).as_posix(),
        content=content,
        start_line=start_line,
        end_line=end_line,
        total_lines=total_lines,
        truncated=truncated,
        warnings=warnings,
    )


def search_code(
    project_path: str | Path,
    query: str,
    globs: list[str] | None = None,
    max_matches: int = MAX_SEARCH_MATCHES,
) -> SearchCodeResult:
    """Search project files for a literal query, preferring ripgrep when available."""

    root = _resolve_project_root(project_path)
    if not query:
        raise ReadOnlyToolError("Search query must not be empty.")

    if shutil.which("rg"):
        result = _search_with_rg(root, query, globs, max_matches)
        if result is not None:
            return result

    return _search_with_python(root, query, globs, max_matches)


def _resolve_project_root(project_path: str | Path) -> Path:
    root = Path(project_path).expanduser().resolve()
    if not root.exists():
        raise ProjectScanError(f"Project path does not exist: {root}")
    if not root.is_dir():
        raise ProjectScanError(f"Project path is not a directory: {root}")
    return root


def _resolve_project_file(project_path: str | Path, relative_path: str) -> tuple[Path, Path]:
    root = _resolve_project_root(project_path)
    candidate = (root / relative_path).resolve()
    if not candidate.is_relative_to(root):
        raise ReadOnlyToolError("Path traversal outside the project root is not allowed.")
    if not candidate.exists():
        raise ReadOnlyToolError(f"File does not exist: {relative_path}")
    if not candidate.is_file():
        raise ReadOnlyToolError(f"Path is not a file: {relative_path}")
    return root, candidate


def _ensure_not_sensitive(path: Path) -> None:
    name = path.name.lower()
    if name in SENSITIVE_FILE_NAMES or name.startswith(".env."):
        raise ReadOnlyToolError(f"Refusing to read sensitive file: {path.name}")
    if name.endswith(SENSITIVE_SUFFIXES):
        raise ReadOnlyToolError(f"Refusing to read sensitive file: {path.name}")


def _normalize_line_range(line_range: tuple[int, int] | None, total_lines: int) -> tuple[int, int]:
    if total_lines == 0:
        return 1, 1
    if line_range is None:
        return 1, total_lines
    start_line, end_line = line_range
    if start_line < 1 or end_line < start_line:
        raise ReadOnlyToolError("Invalid line range.")
    return start_line, min(end_line, total_lines)


def _search_with_rg(
    root: Path,
    query: str,
    globs: list[str] | None,
    max_matches: int,
) -> SearchCodeResult | None:
    command = [
        "rg",
        "--fixed-strings",
        "--line-number",
        "--no-heading",
        "--color",
        "never",
        "--max-count",
        str(max_matches),
    ]
    for directory in sorted(IGNORED_DIRECTORIES):
        command.extend(["--glob", f"!{directory}/**"])
    for name in sorted(SENSITIVE_FILE_NAMES):
        command.extend(["--glob", f"!{name}"])
    command.extend(["--glob", "!.env.*"])
    for suffix in SENSITIVE_SUFFIXES:
        command.extend(["--glob", f"!*{suffix}"])
    for pattern in globs or []:
        command.extend(["--glob", pattern])
    command.append(query)

    try:
        completed = subprocess.run(command, cwd=root, capture_output=True, text=True, check=False)
    except OSError:
        return None

    if completed.returncode not in {0, 1}:
        return SearchCodeResult(
            query=query,
            used_backend="rg",
            warnings=[completed.stderr.strip() or "ripgrep search failed."],
        )

    matches = [_parse_rg_line(line) for line in completed.stdout.splitlines()]
    return SearchCodeResult(
        query=query,
        matches=[match for match in matches if match is not None][:max_matches],
        used_backend="rg",
    )


def _parse_rg_line(line: str) -> SearchCodeMatch | None:
    parts = line.split(":", 2)
    if len(parts) != 3:
        return None
    path, line_number, content = parts
    try:
        parsed_line_number = int(line_number)
    except ValueError:
        return None
    return SearchCodeMatch(path=path, line_number=parsed_line_number, line=content.strip())


def _search_with_python(
    root: Path,
    query: str,
    globs: list[str] | None,
    max_matches: int,
) -> SearchCodeResult:
    matches: list[SearchCodeMatch] = []
    warnings: list[str] = []
    for path in sorted(root.rglob("*")):
        if len(matches) >= max_matches:
            break
        if not path.is_file() or _is_ignored_path(root, path) or _matches_sensitive_name(path):
            continue
        relative = path.relative_to(root).as_posix()
        if globs and not any(fnmatch.fnmatch(relative, pattern) for pattern in globs):
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as exc:
            warnings.append(f"Could not read {relative}: {exc}.")
            continue
        for line_number, line in enumerate(lines, start=1):
            if query in line:
                matches.append(SearchCodeMatch(path=relative, line_number=line_number, line=line.strip()))
                if len(matches) >= max_matches:
                    break
    return SearchCodeResult(query=query, matches=matches, used_backend="python", warnings=warnings)


def _is_ignored_path(root: Path, path: Path) -> bool:
    relative_parts = path.relative_to(root).parts
    return any(part in IGNORED_DIRECTORIES for part in relative_parts)


def _matches_sensitive_name(path: Path) -> bool:
    name = path.name.lower()
    return name in SENSITIVE_FILE_NAMES or name.startswith(".env.") or name.endswith(SENSITIVE_SUFFIXES)
