from __future__ import annotations

import json
from pathlib import Path

from code_reader_agent.memory.project_memory import build_project_memory
from code_reader_agent.models import ProjectMemory, ProjectMemoryOverview, SessionMemory, SessionMemoryTurn
from code_reader_agent.runtime.llm_client import DEFAULT_API_KEY_ENV, DEFAULT_BASE_URL_ENV
from code_reader_agent.repo_map.builder import build_repo_map
from code_reader_agent.runtime.ask_mode import classify_ask_intent, run_ask_mode, run_ask_mode_events
from code_reader_agent.scanner import scan_project
from tests.test_scanner import write_minimal_java_project, write_minimal_vue_project


def disable_llm_env(monkeypatch: object) -> None:
    monkeypatch.delenv(DEFAULT_API_KEY_ENV, raising=False)
    monkeypatch.delenv(DEFAULT_BASE_URL_ENV, raising=False)


def test_classify_ask_intent_covers_supported_question_types() -> None:
    memory = ProjectMemory(
        project_id="project-memory-test",
        project_name="demo",
        project_path="/tmp/demo",
        project_memory=ProjectMemoryOverview(positioning="demo", tech_stack=["Vue"], modules=["Auth"]),
    )

    assert classify_ask_intent("这个项目是做什么的？", memory) == "project_overview"
    assert classify_ask_intent("权限模块怎么实现？", memory) == "module_explanation"
    assert classify_ask_intent("UserController 是做什么的？", memory) == "file_explanation"
    assert classify_ask_intent("登录流程怎么走？", memory) == "flow_trace"
    assert classify_ask_intent("这个接口在哪里被调用？", memory) == "api_lookup"
    assert classify_ask_intent("数据库配置在哪里？", memory) == "config_lookup"
    assert classify_ask_intent("项目用了哪些框架和技术栈？", memory) == "tech_stack"
    assert classify_ask_intent("listUsers 方法在哪里？", memory) == "symbol_lookup"


def test_project_memory_builds_api_index_from_java_and_frontend_calls(tmp_path: Path) -> None:
    write_minimal_java_project(tmp_path)
    controller = tmp_path / "src" / "main" / "java" / "com" / "example" / "demo" / "UserController.java"
    controller.write_text(
        "package com.example.demo;\n\n"
        "import org.springframework.web.bind.annotation.GetMapping;\n"
        "import org.springframework.web.bind.annotation.RestController;\n\n"
        "@RestController\n"
        "public class UserController {\n"
        "  @GetMapping(\"/api/users\")\n"
        "  public String listUsers() { return \"ok\"; }\n"
        "}\n",
        encoding="utf-8",
    )
    (tmp_path / "src" / "api").mkdir(parents=True)
    (tmp_path / "src" / "api" / "user.ts").write_text("export const users = () => fetch('/api/users');\n", encoding="utf-8")

    repo_map = build_repo_map(scan_project(tmp_path))
    memory = build_project_memory(repo_map)

    assert memory.project_memory.positioning
    assert memory.module_summaries
    assert memory.file_summaries
    assert any(file.hash for file in memory.file_summaries)
    assert any(item.name == "UserController" and item.file_path.endswith("UserController.java") for item in memory.symbol_index)
    assert any(entry.path == "/api/users" and entry.backend_method == "listUsers" for entry in memory.api_index)
    assert any("src/api/user.ts" in entry.frontend_calls for entry in memory.api_index)
    assert memory.flow_index


def test_ask_mode_overview_uses_project_memory_without_tools(tmp_path: Path, monkeypatch: object) -> None:
    disable_llm_env(monkeypatch)
    monkeypatch.setenv("CODEREADER_STATE_DIR", str(tmp_path / "state"))
    write_minimal_vue_project(tmp_path)

    result = run_ask_mode(str(tmp_path), "这个项目是做什么的？")

    assert result.intent == "project_overview"
    assert result.answer
    assert result.tool_calls == []
    assert result.used_llm is False
    assert result.fallback_used is True
    assert result.fallback_reason
    assert "Missing" in result.fallback_reason
    assert result.resolved_query
    assert result.context_pack
    assert result.context_pack.project_context
    assert result.session_memory.turns[-1].intent == "project_overview"


def test_ask_mode_file_question_reads_real_file_and_records_reason(tmp_path: Path, monkeypatch: object) -> None:
    disable_llm_env(monkeypatch)
    monkeypatch.setenv("CODEREADER_STATE_DIR", str(tmp_path / "state"))
    write_minimal_java_project(tmp_path)

    result = run_ask_mode(str(tmp_path), "UserController 是做什么的？")

    assert result.intent == "file_explanation"
    assert "src/main/java/com/example/demo/UserController.java" in result.related_files
    assert any(call.tool_name == "read_file" and call.reason for call in result.tool_calls)
    assert any(call.tool_name == "read_file" and call.timestamp and call.duration_ms is not None for call in result.tool_calls)
    assert any(call.tool_name == "read_file" and call.input.get("relative_path") for call in result.tool_calls)
    assert any(ref.path.endswith("UserController.java") for ref in result.references)
    assert result.tool_plan and result.tool_plan.need_tools is True
    assert result.context_pack and result.context_pack.code_evidence


def test_ask_mode_rereads_current_workspace_code_after_file_changes(tmp_path: Path, monkeypatch: object) -> None:
    disable_llm_env(monkeypatch)
    monkeypatch.setenv("CODEREADER_STATE_DIR", str(tmp_path / "state"))
    write_minimal_java_project(tmp_path)
    controller = tmp_path / "src" / "main" / "java" / "com" / "example" / "demo" / "UserController.java"

    first = run_ask_mode(str(tmp_path), "UserController 是做什么的？")
    controller.write_text(
        "package com.example.demo;\n"
        "import org.springframework.web.bind.annotation.GetMapping;\n"
        "import org.springframework.web.bind.annotation.RestController;\n"
        "@RestController\n"
        "public class UserController {\n"
        "  @GetMapping(\"/users\")\n"
        "  public String changedUsers() { return \"changed-live-code\"; }\n"
        "}\n",
        encoding="utf-8",
    )

    second = run_ask_mode(str(tmp_path), "UserController 是做什么的？", session_memory=first.session_memory)

    tool_snippets = [item.code_snippet or "" for item in second.code_evidence if item.source == "tool"]
    assert any("changed-live-code" in snippet for snippet in tool_snippets)
    assert any(call.tool_name == "read_file" for call in second.tool_calls)


def test_ask_mode_followup_uses_session_memory_for_api_question(tmp_path: Path, monkeypatch: object) -> None:
    disable_llm_env(monkeypatch)
    monkeypatch.setenv("CODEREADER_STATE_DIR", str(tmp_path / "state"))
    write_minimal_vue_project(tmp_path)
    (tmp_path / "src" / "api").mkdir(parents=True)
    (tmp_path / "src" / "api" / "auth.ts").write_text("export const login = () => fetch('/api/login');\n", encoding="utf-8")

    first = run_ask_mode(str(tmp_path), "登录流程怎么走？")
    second = run_ask_mode(str(tmp_path), "那这个接口在哪里调用？", session_memory=first.session_memory)

    assert second.intent == "api_lookup"
    assert second.resolved_query
    assert "上一轮上下文" in second.resolved_query.resolved_question
    assert second.session_memory.turns[-2].intent == "flow_trace"
    assert second.session_memory.turns[-1].intent == "api_lookup"
    assert second.session_memory.last_resolved_question == second.resolved_query.resolved_question
    assert any(call.tool_name in {"parse_api_calls", "search_api_path"} for call in second.tool_calls)


def test_ask_mode_api_result_is_json_serializable(tmp_path: Path, monkeypatch: object) -> None:
    disable_llm_env(monkeypatch)
    monkeypatch.setenv("CODEREADER_STATE_DIR", str(tmp_path / "state"))
    write_minimal_vue_project(tmp_path)

    result = run_ask_mode(str(tmp_path), "项目用了哪些框架？")

    assert json.loads(result.model_dump_json())["intent"] == "tech_stack"
    assert json.loads(result.model_dump_json())["context_pack"]["project_context"]


def test_ask_mode_accepts_legacy_session_intent_for_followup(tmp_path: Path, monkeypatch: object) -> None:
    disable_llm_env(monkeypatch)
    monkeypatch.setenv("CODEREADER_STATE_DIR", str(tmp_path / "state"))
    write_minimal_vue_project(tmp_path)
    legacy = SessionMemory(
        project_id="legacy",
        focused_files=["src/main.ts"],
        turns=[
            SessionMemoryTurn(
                question="登录流程怎么走？",
                intent="call_chain",
                referenced_files=["src/main.ts"],
                referenced_apis=["/api/login"],
                answer_summary="登录流程候选。",
            )
        ],
    )

    result = run_ask_mode(str(tmp_path), "那继续解释", session_memory=legacy)

    assert result.resolved_query
    assert "src/main.ts" in result.resolved_query.referenced_files
    assert result.intent == "flow_trace"


def test_context_pack_budget_trims_large_evidence(tmp_path: Path, monkeypatch: object) -> None:
    disable_llm_env(monkeypatch)
    monkeypatch.setenv("CODEREADER_STATE_DIR", str(tmp_path / "state"))
    write_minimal_java_project(tmp_path)
    controller = tmp_path / "src" / "main" / "java" / "com" / "example" / "demo" / "UserController.java"
    controller.write_text(controller.read_text(encoding="utf-8") + "\n".join(f"// marker {index}" for index in range(900)), encoding="utf-8")

    result = run_ask_mode(str(tmp_path), "UserController 具体实现是什么？")

    assert result.context_pack
    assert len(result.context_pack.context_text) <= 12_000
    assert result.context_pack.code_evidence


def test_ask_mode_uses_llm_answer_when_configured(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.setenv("CODEREADER_STATE_DIR", str(tmp_path / "state"))
    write_minimal_vue_project(tmp_path)

    class FakeConfig:
        model = "glm-test"

    class FakeClient:
        config = FakeConfig()

        def __init__(self, model: str) -> None:
            self.model = model

        def is_configured(self) -> bool:
            return True

        def missing_environment_variables(self) -> list[str]:
            return []

        def complete(self, messages: list[dict[str, object]], tools: list[dict[str, object]]) -> dict[str, object]:
            assert tools == []
            assert "Context Pack" in str(messages[-1]["content"])
            return {"choices": [{"message": {"content": "这是来自真实 LLM 路径的 Ask 回答。"}}]}

    monkeypatch.setattr("code_reader_agent.runtime.ask_mode.LiteLLMClient", FakeClient)

    result = run_ask_mode(str(tmp_path), "这个项目是做什么的？")

    assert result.used_llm is True
    assert result.fallback_used is False
    assert result.llm_model == "glm-test"
    assert result.answer == "这是来自真实 LLM 路径的 Ask 回答。"


def test_ask_mode_stream_events_include_public_node_progress(tmp_path: Path, monkeypatch: object) -> None:
    disable_llm_env(monkeypatch)
    monkeypatch.setenv("CODEREADER_STATE_DIR", str(tmp_path / "state"))
    write_minimal_java_project(tmp_path)

    events = list(run_ask_mode_events(str(tmp_path), "UserController 是做什么的？"))

    trace_nodes = [event.get("node") for event in events if event["type"] == "trace"]
    assert "QueryRewriter" in trace_nodes
    assert "IntentClassifier" in trace_nodes
    assert "ToolPlanner" in trace_nodes
    assert "AnswerComposer" in trace_nodes
    assert any(event["type"] == "tool_plan" for event in events)
    assert any(event["type"] == "tool_result" for event in events)
    assert events[-1]["type"] == "final"
    assert events[-1]["event"]["intent"] == "file_explanation"
