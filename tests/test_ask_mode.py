from __future__ import annotations

import json
from pathlib import Path

from code_reader_agent.memory.project_memory import build_project_memory
from code_reader_agent.models import ProjectMemory, ProjectMemoryOverview
from code_reader_agent.repo_map.builder import build_repo_map
from code_reader_agent.runtime.ask_mode import classify_ask_intent, run_ask_mode
from code_reader_agent.scanner import scan_project
from tests.test_scanner import write_minimal_java_project, write_minimal_vue_project


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
    assert classify_ask_intent("登录流程怎么走？", memory) == "call_chain"
    assert classify_ask_intent("这个接口在哪里被调用？", memory) == "api_usage"
    assert classify_ask_intent("数据库配置在哪里？", memory) == "configuration"
    assert classify_ask_intent("项目用了哪些框架和技术栈？", memory) == "tech_stack"


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
    assert any(entry.path == "/api/users" and entry.backend_method == "listUsers" for entry in memory.api_index)
    assert any("src/api/user.ts" in entry.frontend_calls for entry in memory.api_index)


def test_ask_mode_overview_uses_project_memory_without_tools(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.setenv("CODEREADER_STATE_DIR", str(tmp_path / "state"))
    write_minimal_vue_project(tmp_path)

    result = run_ask_mode(str(tmp_path), "这个项目是做什么的？")

    assert result.intent == "project_overview"
    assert result.answer
    assert result.tool_calls == []
    assert result.session_memory.turns[-1].intent == "project_overview"


def test_ask_mode_file_question_reads_real_file_and_records_reason(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.setenv("CODEREADER_STATE_DIR", str(tmp_path / "state"))
    write_minimal_java_project(tmp_path)

    result = run_ask_mode(str(tmp_path), "UserController 是做什么的？")

    assert result.intent == "file_explanation"
    assert "src/main/java/com/example/demo/UserController.java" in result.related_files
    assert any(call.tool_name == "read_file" and call.reason for call in result.tool_calls)
    assert any(ref.path.endswith("UserController.java") for ref in result.references)


def test_ask_mode_followup_uses_session_memory_for_api_question(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.setenv("CODEREADER_STATE_DIR", str(tmp_path / "state"))
    write_minimal_vue_project(tmp_path)
    (tmp_path / "src" / "api").mkdir(parents=True)
    (tmp_path / "src" / "api" / "auth.ts").write_text("export const login = () => fetch('/api/login');\n", encoding="utf-8")

    first = run_ask_mode(str(tmp_path), "登录流程怎么走？")
    second = run_ask_mode(str(tmp_path), "那这个接口在哪里调用？", session_memory=first.session_memory)

    assert second.intent == "api_usage"
    assert second.session_memory.turns[-2].intent == "call_chain"
    assert second.session_memory.turns[-1].intent == "api_usage"
    assert any(call.tool_name in {"parse_api_calls", "search_keyword"} for call in second.tool_calls)


def test_ask_mode_api_result_is_json_serializable(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.setenv("CODEREADER_STATE_DIR", str(tmp_path / "state"))
    write_minimal_vue_project(tmp_path)

    result = run_ask_mode(str(tmp_path), "项目用了哪些框架？")

    assert json.loads(result.model_dump_json())["intent"] == "tech_stack"
