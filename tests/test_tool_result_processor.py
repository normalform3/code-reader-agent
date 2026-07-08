from __future__ import annotations

from code_reader_agent.models import ApiIndexEntry, ReadFileResult, SearchCodeMatch, SearchCodeResult
from code_reader_agent.tools.result_processor import ToolResultProcessor


def test_result_processor_trims_read_file_snippet() -> None:
    processor = ToolResultProcessor()
    raw = ReadFileResult(
        path="src/Large.java",
        content="x" * 5_000,
        start_line=1,
        end_line=200,
        total_lines=200,
    )

    result = processor.process(tool_name="read_file", raw_output=raw, args={"relative_path": raw.path}, reason="Need key excerpt.")

    assert result.success is True
    assert result.evidence
    assert result.evidence[0].code_snippet
    assert len(result.evidence[0].code_snippet) < len(raw.content)
    assert "[truncated]" in result.evidence[0].code_snippet


def test_result_processor_converts_search_matches_to_evidence() -> None:
    processor = ToolResultProcessor()
    raw = SearchCodeResult(
        query="login",
        used_backend="python",
        matches=[SearchCodeMatch(path="src/api/auth.ts", line_number=3, line="fetch('/api/login')")],
    )

    result = processor.process(tool_name="search_keyword", raw_output=raw, args={"keyword": "login"}, reason="Locate login.")

    assert result.output_summary == "Found 1 matches."
    assert result.references[0].path == "src/api/auth.ts"
    assert result.evidence[0].file_path == "src/api/auth.ts"
    assert result.evidence[0].code_snippet == "fetch('/api/login')"


def test_result_processor_converts_index_results_to_memory_evidence() -> None:
    processor = ToolResultProcessor()
    raw = [ApiIndexEntry(path="/api/login", method="POST", backend_file="src/AuthController.java")]

    result = processor.process(tool_name="query_api_index", raw_output=raw, args={"api_path_or_keyword": "login"}, reason="Query API index.")

    assert result.success is True
    assert result.output_summary == "Found 1 index candidates."
    assert result.evidence[0].source == "memory"
    assert result.evidence[0].api == "/api/login"
    assert result.evidence[0].file_path == "src/AuthController.java"
