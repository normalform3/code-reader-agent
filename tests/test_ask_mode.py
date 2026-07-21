from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from code_reader_agent.memory.project_memory import build_project_memory
from code_reader_agent.models import ProjectMemory, ProjectMemoryOverview, SessionMemory, SessionMemoryTurn
from code_reader_agent.repo_map.builder import build_repo_map
from code_reader_agent.runtime.ask_mode import AskWorkflowUnavailableError, classify_ask_intent, run_ask_mode, run_ask_mode_events
from code_reader_agent.scanner import scan_project
from tests.test_scanner import write_minimal_java_project, write_minimal_vue_project


class FakeConfig:
    model = "glm-test"


class ScriptedAskClient:
    """Shared scripted responses because Ask creates a client per graph node."""

    config = FakeConfig()
    responses: list[dict[str, Any]] = []
    received_tools: list[list[dict[str, Any]]] = []

    def __init__(self, model: str) -> None:
        self.model = model

    def is_configured(self) -> bool:
        return True

    def missing_environment_variables(self) -> list[str]:
        return []

    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
        self.received_tools.append(tools)
        if not self.responses:
            raise RuntimeError("Fake LLM has no response left")
        return self.responses.pop(0)


def llm_response(content: str, tool_calls: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {"choices": [{"message": {"content": content, "tool_calls": tool_calls or []}}]}


def tool_call(name: str, arguments: dict[str, object], call_id: str = "tool-1") -> dict[str, Any]:
    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}


def intent_response(intent: str, *, need_code_evidence: bool = False) -> dict[str, Any]:
    return llm_response(
        json.dumps(
            {
                "intent": intent,
                "keywords": [],
                "possible_files": [],
                "possible_apis": [],
                "possible_symbols": [],
                "need_code_evidence": need_code_evidence,
            }
        )
    )


def configure_llm(monkeypatch: pytest.MonkeyPatch, responses: list[dict[str, Any]]) -> None:
    ScriptedAskClient.responses = list(responses)
    ScriptedAskClient.received_tools = []
    monkeypatch.setattr("code_reader_agent.runtime.ask_mode.LiteLLMClient", ScriptedAskClient)


def default_responses(intent: str = "project_overview") -> list[dict[str, Any]]:
    return [intent_response(intent), llm_response("证据已足够。"), llm_response("这是基于 Context Pack 的回答。")]


def test_classify_ask_intent_covers_supported_question_types() -> None:
    memory = ProjectMemory(project_id="test", project_name="demo", project_path="/tmp/demo", project_memory=ProjectMemoryOverview(positioning="demo", tech_stack=["Vue"], modules=["Auth"]))

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
    controller = tmp_path / "src/main/java/com/example/demo/UserController.java"
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
    (tmp_path / "src/api").mkdir(parents=True)
    (tmp_path / "src/api/user.ts").write_text("export const users = () => fetch('/api/users');\n", encoding="utf-8")

    memory = build_project_memory(build_repo_map(scan_project(tmp_path)))

    assert any(item.name == "UserController" and item.file_path.endswith("UserController.java") for item in memory.symbol_index)
    assert any(entry.path == "/api/users" and entry.backend_method == "listUsers" for entry in memory.api_index)


def test_ask_uses_langgraph_llm_intent_and_multi_round_tool_loop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CODEREADER_STATE_DIR", str(tmp_path / "state"))
    write_minimal_java_project(tmp_path)
    configure_llm(
        monkeypatch,
        [
            intent_response("file_explanation", need_code_evidence=True),
            llm_response("需要读取 Controller 源码。", [tool_call("read_file", {"relative_path": "src/main/java/com/example/demo/UserController.java", "start_line": 1, "end_line": 80})]),
            llm_response("证据已足够。"),
            llm_response("UserController 是接口入口，依据已读取的源码片段。"),
        ],
    )

    result = run_ask_mode(str(tmp_path), "UserController 是做什么的？")

    assert result.intent == "file_explanation"
    assert result.used_llm is True
    assert result.fallback_used is False
    assert any(call.tool_name == "read_file" and call.reason for call in result.tool_calls)
    assert result.tool_plan and [call.tool_name for call in result.tool_plan.tool_calls] == ["read_file"]
    assert any(ref.path.endswith("UserController.java") for ref in result.references)
    assert any(event.stage == "LLM Tool Planner" for event in result.trace_events)
    assert any(tools for tools in ScriptedAskClient.received_tools)


def test_ask_returns_unavailable_error_without_llm(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CODEREADER_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.delenv("DASHSCOPE_BASE_URL", raising=False)
    write_minimal_vue_project(tmp_path)

    with pytest.raises(AskWorkflowUnavailableError):
        run_ask_mode(str(tmp_path), "这个项目是做什么的？")


def test_ask_stops_after_tool_budget_and_keeps_partial_evidence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CODEREADER_STATE_DIR", str(tmp_path / "state"))
    write_minimal_vue_project(tmp_path)
    calls = [tool_call("list_files", {"max_depth": 1}, f"tool-{index}") for index in range(8)]
    configure_llm(monkeypatch, [intent_response("project_overview"), llm_response("需要目录证据。", calls), llm_response("项目概览回答。")])

    result = run_ask_mode(str(tmp_path), "这个项目是做什么的？")

    assert len(result.tool_calls) == 8
    assert any("tool planning stopped" in warning for warning in result.warnings)
    assert result.answer == "项目概览回答。"


def test_session_summarizer_archives_turns_and_keeps_recent_window(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CODEREADER_STATE_DIR", str(tmp_path / "state"))
    write_minimal_vue_project(tmp_path)
    session = SessionMemory(
        project_id="session",
        turns=[SessionMemoryTurn(question=f"问题 {index}", intent="project_overview", answer_summary=f"回答 {index}") for index in range(8)],
    )
    configure_llm(monkeypatch, [*default_responses(), llm_response("早期问题围绕项目总览。")])

    result = run_ask_mode(str(tmp_path), "继续介绍", session_memory=session, persist_session_memory=False)

    assert len(result.session_memory.turns) == 8
    assert result.session_memory.archived_turn_count == 1
    assert result.session_memory.history_summary == "早期问题围绕项目总览。"


def test_session_summary_failure_keeps_existing_summary_and_returns_answer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CODEREADER_STATE_DIR", str(tmp_path / "state"))
    write_minimal_vue_project(tmp_path)
    session = SessionMemory(
        project_id="session",
        history_summary="已有历史摘要。",
        turns=[SessionMemoryTurn(question=f"问题 {index}", intent="project_overview", answer_summary=f"回答 {index}") for index in range(8)],
    )
    configure_llm(monkeypatch, [*default_responses(), llm_response("")])

    result = run_ask_mode(str(tmp_path), "继续介绍", session_memory=session, persist_session_memory=False)

    assert result.answer
    assert result.session_memory.history_summary == "已有历史摘要。"
    assert len(result.session_memory.turns) == 8
    assert any("summary failed" in warning for warning in result.warnings)


def test_ask_streams_langgraph_node_progress(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CODEREADER_STATE_DIR", str(tmp_path / "state"))
    write_minimal_java_project(tmp_path)
    configure_llm(
        monkeypatch,
        [
            intent_response("file_explanation", need_code_evidence=True),
            llm_response("读取文件。", [tool_call("read_file", {"relative_path": "src/main/java/com/example/demo/UserController.java"})]),
            llm_response("无需更多工具。"),
            llm_response("回答。"),
        ],
    )

    events = list(run_ask_mode_events(str(tmp_path), "UserController 是做什么的？"))

    trace_nodes = [event.get("node") for event in events if event["type"] == "trace"]
    assert "LLMIntentClassifier" in trace_nodes
    assert "LLMToolPlanner" in trace_nodes
    assert "SessionSummarizer" in trace_nodes
    assert any(event["type"] == "tool_result" for event in events)
    assert events[-1]["type"] == "final"


def write_feature_flow_project(root: Path, *, include_mapper: bool = True) -> None:
    (root / "frontend" / "src" / "views").mkdir(parents=True)
    (root / "backend" / "src" / "main" / "java" / "com" / "example" / "demo").mkdir(parents=True)
    (root / "frontend" / "package.json").write_text(
        json.dumps({"name": "flow-web", "dependencies": {"vue": "^3.5.0"}}), encoding="utf-8"
    )
    (root / "backend" / "pom.xml").write_text(
        "<project><artifactId>flow-api</artifactId><dependencies><dependency><artifactId>spring-boot-starter-web</artifactId></dependency></dependencies></project>",
        encoding="utf-8",
    )
    (root / "frontend" / "src" / "views" / "LoginView.vue").write_text(
        "<script setup>\nconst login = () => fetch('/api/login')\n</script>\n<template><button @click=\"login\" /></template>\n",
        encoding="utf-8",
    )
    package = root / "backend" / "src" / "main" / "java" / "com" / "example" / "demo"
    (package / "AuthController.java").write_text(
        "@RestController\npublic class AuthController { private final AuthService authService; @PostMapping(\"/api/login\") public String login() { return authService.login(); } }\n",
        encoding="utf-8",
    )
    (package / "AuthService.java").write_text(
        "@Service\npublic class AuthService { private final UserMapper userMapper; public String login() { return userMapper.findUser(); } }\n",
        encoding="utf-8",
    )
    if include_mapper:
        (package / "UserMapper.java").write_text(
            "@Mapper\npublic interface UserMapper { String findUser(); }\n",
            encoding="utf-8",
        )


def test_flow_investigation_returns_complete_evidence_chain(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CODEREADER_STATE_DIR", str(tmp_path / "state"))
    write_feature_flow_project(tmp_path)
    frontend = "frontend/src/views/LoginView.vue"
    controller = "backend/src/main/java/com/example/demo/AuthController.java"
    service = "backend/src/main/java/com/example/demo/AuthService.java"
    mapper = "backend/src/main/java/com/example/demo/UserMapper.java"
    configure_llm(
        monkeypatch,
        [
            intent_response("flow_trace", need_code_evidence=True),
            llm_response(
                "读取端到端链路。",
                [
                    tool_call("read_file", {"relative_path": frontend}, "flow-1"),
                    tool_call("read_file", {"relative_path": controller}, "flow-2"),
                    tool_call("read_file", {"relative_path": service}, "flow-3"),
                    tool_call("read_file", {"relative_path": mapper}, "flow-4"),
                ],
            ),
            llm_response("证据已充分。"),
        ],
    )

    result = run_ask_mode(str(tmp_path), "登录功能的数据如何流转？")

    assert result.investigation is not None
    assert result.investigation.status == "complete"
    assert all(item.status == "satisfied" for item in result.investigation.plan)
    assert result.investigation.flow_steps
    assert all(step.status == "confirmed" and step.evidence for step in result.investigation.flow_steps)
    assert all(finding.evidence for finding in result.investigation.findings if finding.status == "confirmed")
    assert any(event.stage == "Goal Planner" for event in result.trace_events)
    assert any(event.stage == "Evidence Reviewer" for event in result.trace_events)
    assert any(event.stage == "Investigation Reporter" for event in result.trace_events)


def test_flow_investigation_marks_missing_stage_partial_after_replanning(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CODEREADER_STATE_DIR", str(tmp_path / "state"))
    write_feature_flow_project(tmp_path, include_mapper=False)
    configure_llm(
        monkeypatch,
        [
            intent_response("flow_trace", need_code_evidence=True),
            llm_response(
                "先读取后端实现。",
                [
                    tool_call("read_file", {"relative_path": "backend/src/main/java/com/example/demo/AuthController.java"}, "partial-1"),
                    tool_call("read_file", {"relative_path": "backend/src/main/java/com/example/demo/AuthService.java"}, "partial-2"),
                ],
            ),
            llm_response("当前没有更多可读证据。"),
            llm_response("当前没有更多可读证据。"),
        ],
    )

    events = list(run_ask_mode_events(str(tmp_path), "登录流程怎么走？"))
    result = next(event["event"] for event in events if event["type"] == "final")

    assert result["investigation"]["status"] == "partial"
    assert any(item["status"] == "missing" for item in result["investigation"]["plan"])
    assert any(event["type"] == "goal_plan" for event in events)
    assert any(event["type"] == "evidence_review" for event in events)
    assert any(event["type"] == "replan" for event in events)
    assert any(event["type"] == "answer" and event.get("node") == "InvestigationReporter" for event in events)
