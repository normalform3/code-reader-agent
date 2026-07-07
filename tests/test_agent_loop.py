from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from code_reader_agent.runtime.agent_loop import run_agent_loop
from tests.test_scanner import write_minimal_java_project, write_minimal_vue_project


class FakeLLMClient:
    def __init__(self, responses: list[dict[str, Any]] | None = None, error: Exception | None = None) -> None:
        self.responses = responses or []
        self.error = error
        self.calls = 0
        self.messages: list[dict[str, Any]] = []

    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
        self.calls += 1
        self.messages = messages
        if self.error:
            raise self.error
        index = min(self.calls - 1, len(self.responses) - 1)
        return self.responses[index]


def tool_call_response(name: str, arguments: dict[str, Any], call_id: str = "call_1") -> dict[str, Any]:
    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": call_id,
                            "type": "function",
                            "function": {"name": name, "arguments": json.dumps(arguments)},
                        }
                    ],
                }
            }
        ]
    }


def final_response(payload: dict[str, Any]) -> dict[str, Any]:
    return {"choices": [{"message": {"role": "assistant", "content": json.dumps(payload, ensure_ascii=False)}}]}


def test_agent_loop_executes_tool_and_parses_final_answer(tmp_path: Path) -> None:
    write_minimal_vue_project(tmp_path)
    client = FakeLLMClient(
        [
            tool_call_response("read_file", {"relative_path": "package.json"}),
            final_response(
                {
                    "answer": "这是一个 Vue 项目，package.json 提供了运行脚本。",
                    "skill": "project_overview_skill",
                    "evidence": [
                        {
                            "path": "package.json",
                            "reason": "读取到 package.json。",
                            "source": "read_file",
                        }
                    ],
                    "read_files": ["package.json"],
                    "warnings": [],
                    "suggested_questions": ["怎么运行？"],
                }
            ),
        ]
    )

    result = run_agent_loop(str(tmp_path), "这个项目是干什么的？", llm_client=client)

    assert result.used_llm is True
    assert result.fallback_used is False
    assert "Vue 项目" in result.final_answer
    assert "package.json" in result.read_files
    assert any(call.tool_name == "read_file" and call.status == "success" for call in result.tool_calls)
    assert any(step.kind == "tool" for step in result.agent_steps)
    assert any(event.stage == "Tool Executor" and event.tool_name == "read_file" for event in result.trace_events)
    assert "VueSkill" in result.selected_skills
    assert result.project_manual.title.endswith("项目说明书")
    assert result.project_manual.overview is not None
    assert any(item.name == "Vue" for item in result.project_manual.technology_stack)
    assert result.project_manual.modules
    assert result.project_manual.entrypoints
    assert result.project_manual.directory_tree
    assert result.report.title.endswith("项目解读报告")


def test_agent_loop_uses_fallback_on_llm_error(tmp_path: Path) -> None:
    write_minimal_vue_project(tmp_path)

    result = run_agent_loop(str(tmp_path), "这个项目是干什么的？", llm_client=FakeLLMClient(error=RuntimeError("boom")))

    assert result.used_llm is False
    assert result.fallback_used is True
    assert any("LLM agent loop failed" in warning for warning in result.warnings)
    assert result.analysis_plan
    assert result.context_snapshot.evidence_count > 0
    assert result.project_manual.key_directories
    assert result.report.module_summaries
    assert any(event.stage == "Report Writer" for event in result.trace_events)


def test_agent_loop_records_sensitive_file_rejection(tmp_path: Path) -> None:
    write_minimal_vue_project(tmp_path)
    (tmp_path / ".env").write_text("SECRET=value\n", encoding="utf-8")
    client = FakeLLMClient(
        [
            tool_call_response("read_file", {"relative_path": ".env"}),
            final_response(
                {
                    "answer": "无法读取敏感文件。",
                    "skill": "project_overview_skill",
                    "evidence": [],
                    "read_files": [],
                    "warnings": ["敏感文件被拒绝。"],
                    "suggested_questions": [],
                }
            ),
        ]
    )

    result = run_agent_loop(str(tmp_path), "读 .env", llm_client=client)

    assert result.used_llm is True
    assert any(call.tool_name == "read_file" and call.status == "error" for call in result.tool_calls)
    assert any("sensitive" in warning.lower() or "敏感" in warning for warning in result.warnings)


def test_agent_loop_uses_fallback_when_final_json_invalid(tmp_path: Path) -> None:
    write_minimal_vue_project(tmp_path)
    client = FakeLLMClient([{"choices": [{"message": {"role": "assistant", "content": "not json"}}]}])

    result = run_agent_loop(str(tmp_path), "这个项目是干什么的？", llm_client=client)

    assert result.fallback_used is True
    assert any("not valid JSON" in warning for warning in result.warnings)


def test_agent_loop_uses_fallback_after_max_steps(tmp_path: Path) -> None:
    write_minimal_vue_project(tmp_path)
    client = FakeLLMClient([tool_call_response("search_code", {"query": "vue"})])

    result = run_agent_loop(str(tmp_path), "找 Vue", max_steps=1, llm_client=client)

    assert result.fallback_used is True
    assert any("max_steps=1" in warning for warning in result.warnings)


def test_agent_loop_selects_spring_boot_skill_and_report_for_java(tmp_path: Path) -> None:
    write_minimal_java_project(tmp_path)

    result = run_agent_loop(str(tmp_path), "生成项目解读报告", llm_client=FakeLLMClient(error=RuntimeError("offline")))

    assert "SpringBootSkill" in result.selected_skills
    assert "CodebaseOverviewSkill" in result.selected_skills
    assert any(item.actor == "Planner" for item in result.analysis_plan)
    assert any("Controller" in item or "Services" in item for item in result.report.module_summaries)
    assert result.report.key_entrypoints
    assert result.report.reading_route
    assert result.report.evidence
    assert result.report.uncertainties
    assert any(item.name == "Maven" for item in result.project_manual.technology_stack)
    assert any(module.name in {"Controllers", "Services", "Repositories"} for module in result.project_manual.modules)
    assert any(entry.kind == "java_app_entry" for entry in result.project_manual.entrypoints)


def test_agent_loop_reuses_project_manual_context_for_followup(tmp_path: Path) -> None:
    write_minimal_vue_project(tmp_path)
    first_result = run_agent_loop(str(tmp_path), "生成项目说明书", llm_client=FakeLLMClient(error=RuntimeError("offline")))
    client = FakeLLMClient(error=RuntimeError("offline again"))

    result = run_agent_loop(
        str(tmp_path),
        "路由入口在哪里？",
        llm_client=client,
        project_manual_context=first_result.project_manual,
    )

    assert result.fallback_used is True
    assert any("project_manual_context=" in item for item in result.context_snapshot.memory_context)
