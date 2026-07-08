"""Safe read-only tools for local project inspection."""

from __future__ import annotations

import fnmatch
import re
import shutil
import subprocess
from pathlib import Path

from code_reader_agent.models import FileTreeEntry, ReadFileResult, SearchCodeMatch, SearchCodeResult
from code_reader_agent.scanner import IGNORED_DIRECTORIES, ProjectScanError, scan_project


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


def search_keyword(project_path: str | Path, keyword: str, scope: str | None = None) -> SearchCodeResult:
    """Search a literal keyword, optionally constrained to a coarse project scope."""

    globs = _globs_for_scope(scope)
    return search_code(project_path, keyword, globs=globs)


def search_api_path(project_path: str | Path, api_path: str) -> SearchCodeResult:
    """Search for an API path in likely frontend, backend, and config files."""

    globs = [
        "*.java",
        "*.ts",
        "*.tsx",
        "*.js",
        "*.jsx",
        "*.vue",
        "*.xml",
        "*.yml",
        "*.yaml",
        "*.properties",
    ]
    return search_code(project_path, api_path, globs=globs)


def list_files(project_path: str | Path, max_depth: int | None = None) -> list[FileTreeEntry]:
    """List the safe project file tree using the scanner ignore rules."""

    entries = scan_project(project_path).file_tree
    if max_depth is None:
        return entries
    return [entry for entry in entries if entry.depth <= max_depth]


def search_symbol(project_path: str | Path, symbol: str) -> SearchCodeResult:
    """Search likely source files for a class, function, component, or method name."""

    globs = [
        "*.java",
        "*.ts",
        "*.tsx",
        "*.js",
        "*.jsx",
        "*.vue",
        "*.xml",
    ]
    return search_code(project_path, symbol, globs=globs)


def parse_dependencies(project_path: str | Path) -> dict[str, object]:
    """Parse dependency metadata already supported by the safe scanner."""

    scan = scan_project(project_path)
    return {
        "package_manager": scan.package.package_manager,
        "scripts": scan.package.scripts,
        "frontend_dependencies": scan.package.dependencies,
        "frontend_dev_dependencies": scan.package.dev_dependencies,
        "java_build_tool": scan.java_build.build_tool,
        "java_dependencies": scan.java_build.dependencies,
        "java_config_files": scan.java_build.config_files,
    }


def parse_routes(project_path: str | Path) -> list[dict[str, object]]:
    """Extract lightweight frontend route candidates from router files."""

    scan = scan_project(project_path)
    route_files = [
        entry.path
        for entry in scan.file_tree
        if entry.kind == "file" and ("/router/" in entry.path.lower() or "routes" in entry.path.lower())
    ]
    routes: list[dict[str, object]] = []
    for path in route_files[:20]:
        try:
            result = read_file(project_path, path)
        except ReadOnlyToolError:
            continue
        for line_number, line in enumerate(result.content.splitlines(), start=result.start_line):
            for match in re.finditer(r"path\s*:\s*['\"]([^'\"]+)['\"]", line):
                routes.append({"path": match.group(1), "file": result.path, "line_number": line_number})
    return routes


def parse_api_calls(project_path: str | Path) -> list[dict[str, object]]:
    """Extract lightweight frontend HTTP call candidates."""

    scan = scan_project(project_path)
    source_files = [
        entry.path
        for entry in scan.file_tree
        if entry.kind == "file" and entry.path.endswith((".ts", ".tsx", ".js", ".jsx", ".vue"))
    ]
    calls: list[dict[str, object]] = []
    pattern = re.compile(
        r"(?P<client>axios|fetch|request)\s*(?:\.\s*(?P<method>get|post|put|delete|patch))?\s*\(\s*['\"](?P<path>[^'\"]+)['\"]",
        re.IGNORECASE,
    )
    for path in source_files[:240]:
        try:
            result = read_file(project_path, path)
        except ReadOnlyToolError:
            continue
        for line_number, line in enumerate(result.content.splitlines(), start=result.start_line):
            match = pattern.search(line)
            if not match:
                continue
            method = match.group("method")
            calls.append(
                {
                    "path": match.group("path"),
                    "method": method.upper() if method else None,
                    "client": match.group("client"),
                    "file": result.path,
                    "line_number": line_number,
                }
            )
    return calls


def parse_controller(project_path: str | Path) -> list[dict[str, object]]:
    """Extract lightweight Spring Controller endpoint candidates."""

    scan = scan_project(project_path)
    controller_files = [
        entry.path
        for entry in scan.file_tree
        if entry.kind == "file" and entry.path.endswith("Controller.java")
    ]
    endpoints: list[dict[str, object]] = []
    mapping_pattern = re.compile(
        r"@(?P<annotation>GetMapping|PostMapping|PutMapping|DeleteMapping|PatchMapping|RequestMapping)"
        r"(?:\s*\(\s*(?:value\s*=\s*)?['\"](?P<path>[^'\"]+)['\"])?"
    )
    method_pattern = re.compile(r"(?:public|private|protected)\s+[\w<>, ?]+\s+(?P<method>\w+)\s*\(")
    for path in controller_files[:120]:
        try:
            result = read_file(project_path, path)
        except ReadOnlyToolError:
            continue
        pending: dict[str, object] | None = None
        for line_number, line in enumerate(result.content.splitlines(), start=result.start_line):
            mapping = mapping_pattern.search(line)
            if mapping:
                annotation = mapping.group("annotation")
                http_method = _http_method_for_mapping(annotation)
                pending = {
                    "path": mapping.group("path") or "",
                    "method": http_method,
                    "backend_file": result.path,
                    "line_number": line_number,
                    "backend_method": None,
                }
                endpoints.append(pending)
                continue
            if pending and pending.get("backend_method") is None:
                method = method_pattern.search(line)
                if method:
                    pending["backend_method"] = method.group("method")
    return endpoints


def parse_mapper(project_path: str | Path) -> list[dict[str, object]]:
    """Extract Mapper, Repository, SQL, and XML mapping candidates."""

    scan = scan_project(project_path)
    candidates = [
        entry.path
        for entry in scan.file_tree
        if entry.kind == "file"
        and (
            entry.path.endswith(("Mapper.java", "Repository.java", "Dao.java", "Mapper.xml"))
            or "/mapper/" in entry.path.lower()
            or "/repository/" in entry.path.lower()
        )
    ]
    return [{"path": path, "kind": _mapper_kind(path)} for path in candidates]


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


def _http_method_for_mapping(annotation: str) -> str | None:
    return {
        "GetMapping": "GET",
        "PostMapping": "POST",
        "PutMapping": "PUT",
        "DeleteMapping": "DELETE",
        "PatchMapping": "PATCH",
    }.get(annotation)


def _mapper_kind(path: str) -> str:
    if path.endswith("Mapper.xml"):
        return "mapper_xml"
    if path.endswith("Mapper.java"):
        return "mapper"
    if path.endswith("Repository.java"):
        return "repository"
    if path.endswith("Dao.java"):
        return "dao"
    return "mapping_candidate"


def _globs_for_scope(scope: str | None) -> list[str] | None:
    if scope is None:
        return None
    normalized = scope.lower()
    if normalized in {"frontend", "web", "view"}:
        return ["*.ts", "*.tsx", "*.js", "*.jsx", "*.vue"]
    if normalized in {"backend", "java", "server"}:
        return ["*.java", "*.xml", "*.yml", "*.yaml", "*.properties"]
    if normalized in {"config", "configuration"}:
        return ["*.json", "*.toml", "*.xml", "*.yml", "*.yaml", "*.properties", "*.gradle", "*.kts"]
    return None
