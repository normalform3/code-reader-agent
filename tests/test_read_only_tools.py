from __future__ import annotations

from pathlib import Path

import pytest

from code_reader_agent.tools.read_only import ReadOnlyToolError, read_file, search_code


def test_read_file_returns_line_range(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.ts").write_text("one\ntwo\nthree\n", encoding="utf-8")

    result = read_file(tmp_path, "src/main.ts", line_range=(2, 3))

    assert result.path == "src/main.ts"
    assert result.content == "two\nthree"
    assert result.start_line == 2
    assert result.end_line == 3
    assert result.total_lines == 3


def test_read_file_rejects_path_traversal(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("nope\n", encoding="utf-8")

    with pytest.raises(ReadOnlyToolError, match="Path traversal"):
        read_file(tmp_path, "../outside.txt")


def test_read_file_rejects_sensitive_files(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("TOKEN=secret\n", encoding="utf-8")

    with pytest.raises(ReadOnlyToolError, match="sensitive"):
        read_file(tmp_path, ".env")


def test_read_file_truncates_long_files(tmp_path: Path) -> None:
    (tmp_path / "large.txt").write_text("x" * 13_000, encoding="utf-8")

    result = read_file(tmp_path, "large.txt")

    assert result.truncated is True
    assert len(result.content) == 12_000
    assert result.warnings


def test_search_code_returns_matches(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "api.ts").write_text("export const login = () => fetch('/login');\n", encoding="utf-8")

    result = search_code(tmp_path, "login")

    assert result.matches
    assert result.matches[0].path == "src/api.ts"
    assert result.matches[0].line_number == 1


def test_search_code_returns_empty_matches(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.ts").write_text("console.log('hello');\n", encoding="utf-8")

    result = search_code(tmp_path, "missing")

    assert result.matches == []


def test_search_code_skips_sensitive_files(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("SECRET_TOKEN=needle\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.ts").write_text("console.log('hello');\n", encoding="utf-8")

    result = search_code(tmp_path, "needle")

    assert result.matches == []
