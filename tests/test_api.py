from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

import apps.api.main as api_main
from apps.api.main import app
from code_reader_agent.github_importer import GitHubCloneError
from code_reader_agent.models import AgentRunResult, AgentStep, GitHubImportResult
from tests.test_scanner import write_minimal_java_project, write_vue_spring_monorepo


client = TestClient(app)


def test_scan_project_api_returns_scan_result(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.ts").write_text("console.log('hello');\n", encoding="utf-8")
    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "name": "api-sample",
                "scripts": {"dev": "vite"},
                "dependencies": {"vue": "^3.5.0"},
                "devDependencies": {"vite": "^5.4.0", "typescript": "^5.5.0"},
            }
        ),
        encoding="utf-8",
    )

    response = client.post("/api/projects/scan", json={"project_path": str(tmp_path)})

    assert response.status_code == 200
    payload = response.json()
    assert payload["project_name"] == "api-sample"
    assert payload["package"]["scripts"] == {"dev": "vite"}
    assert {tag["name"] for tag in payload["detected_stack"]} >= {"Vue", "Vite", "TypeScript"}


def test_scan_project_api_returns_java_build_result(tmp_path: Path) -> None:
    write_minimal_java_project(tmp_path)

    response = client.post("/api/projects/scan", json={"project_path": str(tmp_path)})

    assert response.status_code == 200
    payload = response.json()
    assert payload["project_name"] == "demo-service"
    assert payload["java_build"]["found"] is True
    assert payload["java_build"]["build_tool"] == "maven"
    assert payload["java_build"]["artifact_id"] == "demo-service"
    assert "spring-boot-starter-web" in payload["java_build"]["dependencies"]
    assert {tag["name"] for tag in payload["detected_stack"]} >= {"Java", "Maven", "Spring Web"}
    assert {entry["kind"] for entry in payload["entrypoints"]} >= {"java_app_entry", "java_controller"}


def test_repo_map_api_returns_modules(tmp_path: Path) -> None:
    write_minimal_java_project(tmp_path)

    response = client.post("/api/projects/repo-map", json={"project_path": str(tmp_path)})

    assert response.status_code == 200
    payload = response.json()
    assert payload["project_name"] == "demo-service"
    assert payload["project_summary"]["one_liner"]
    assert payload["stack_explanations"]
    assert payload["directory_insights"]
    assert payload["reading_recommendations"]
    assert {module["id"] for module in payload["modules"]} >= {"controller", "service", "repository"}
    assert payload["controllers"] == ["src/main/java/com/example/demo/UserController.java"]
    assert "pom.xml" in {item["path"] for item in payload["evidence"]}
    assert any(item["excerpt"] for item in payload["evidence"] if item["path"] == "pom.xml")


def test_repo_map_api_supports_vue_spring_monorepo_subdirectories(tmp_path: Path) -> None:
    write_vue_spring_monorepo(tmp_path)

    response = client.post("/api/projects/repo-map", json={"project_path": str(tmp_path)})

    assert response.status_code == 200
    payload = response.json()
    assert {tag["name"] for tag in payload["detected_stack"]} >= {"Vue", "Vite", "TypeScript", "Java", "Maven", "Spring Web"}
    assert {module["id"] for module in payload["modules"]} >= {"app", "config", "router", "views", "controller", "service", "repository"}
    assert {
        "frontend/package.json",
        "frontend/vite.config.ts",
        "backend/pom.xml",
        "backend/src/main/java/com/example/demo/DemoApplication.java",
    } <= {item["path"] for item in payload["evidence"]}
    assert "frontend/src/main.ts" in {entry["path"] for entry in payload["entrypoints"]}
    assert "backend/src/main/resources/application.yml" in {entry["path"] for entry in payload["entrypoints"]}


def test_scan_project_api_returns_clear_error_for_invalid_path(tmp_path: Path) -> None:
    response = client.post("/api/projects/scan", json={"project_path": str(tmp_path / "missing")})

    assert response.status_code == 400
    assert "Project path does not exist" in response.json()["detail"]


def test_import_github_project_api_returns_cached_project(monkeypatch: Any, tmp_path: Path) -> None:
    def fake_import_github_repository(github_url: str) -> GitHubImportResult:
        return GitHubImportResult(
            project_name="codex",
            project_path=str(tmp_path / "codex"),
            github_url=github_url,
            repository="openai/codex",
            reused_cache=False,
        )

    monkeypatch.setattr(api_main, "import_github_repository", fake_import_github_repository)

    response = client.post("/api/projects/import-github", json={"github_url": "https://github.com/openai/codex"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["project_name"] == "codex"
    assert payload["repository"] == "openai/codex"
    assert payload["project_path"] == str(tmp_path / "codex")


def test_import_github_project_api_returns_clear_error_for_invalid_url() -> None:
    response = client.post("/api/projects/import-github", json={"github_url": "https://example.com/openai/codex"})

    assert response.status_code == 400
    assert "Only https://github.com" in response.json()["detail"]


def test_import_github_project_api_maps_clone_failure(monkeypatch: Any) -> None:
    def fake_import_github_repository(github_url: str) -> GitHubImportResult:
        raise GitHubCloneError("GitHub repository could not be cloned.")

    monkeypatch.setattr(api_main, "import_github_repository", fake_import_github_repository)

    response = client.post("/api/projects/import-github", json={"github_url": "https://github.com/openai/missing"})

    assert response.status_code == 502
    assert "could not be cloned" in response.json()["detail"]


def test_project_history_crud_does_not_delete_cached_project(monkeypatch: Any, tmp_path: Path) -> None:
    monkeypatch.setenv("CODEREADER_STATE_DIR", str(tmp_path / "state"))
    cached_project = tmp_path / "cached-repo"
    cached_project.mkdir()

    create_response = client.post(
        "/api/projects/history",
        json={
            "project_name": "cached-repo",
            "project_path": str(cached_project),
            "title": "openai/cached-repo",
            "github_url": "https://github.com/openai/cached-repo",
            "repository": "openai/cached-repo",
            "status": "ready",
            "last_question": "介绍项目",
        },
    )

    assert create_response.status_code == 200
    created = create_response.json()
    assert created["title"] == "openai/cached-repo"

    list_response = client.get("/api/projects/history")
    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()] == [created["id"]]

    update_response = client.patch(
        f"/api/projects/history/{created['id']}",
        json={"title": "Renamed", "status": "error", "last_error": "boom"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["title"] == "Renamed"
    assert update_response.json()["last_error"] == "boom"

    delete_response = client.delete(f"/api/projects/history/{created['id']}")
    assert delete_response.status_code == 200
    assert delete_response.json() == {"deleted": True}
    assert cached_project.exists()
    assert client.get("/api/projects/history").json() == []


def test_registry_tools_crud_and_builtin_disable(monkeypatch: Any, tmp_path: Path) -> None:
    monkeypatch.setenv("CODEREADER_STATE_DIR", str(tmp_path / "state"))

    list_response = client.get("/api/registry/tools")
    assert list_response.status_code == 200
    tools = list_response.json()
    assert "read_file" in {item["id"] for item in tools}
    read_file_tool = next(item for item in tools if item["id"] == "read_file")
    assert read_file_tool["builtin"] is True
    assert read_file_tool["details"]
    assert {section["title"] for section in read_file_tool["details"]} >= {"输入", "输出", "安全规则"}

    create_response = client.post(
        "/api/registry/tools",
        json={
            "name": "custom_inspect",
            "description": "Custom read-only inspection.",
            "notes": "Demo only.",
            "details": [{"title": "Input", "items": ["project_path"]}],
        },
    )
    assert create_response.status_code == 200
    custom = create_response.json()
    assert custom["builtin"] is False
    assert custom["details"] == [{"title": "Input", "items": ["project_path"]}]

    update_response = client.patch(
        f"/api/registry/tools/{custom['id']}",
        json={
            "enabled": False,
            "description": "Updated description.",
            "details": [{"title": "Output", "items": ["custom result"]}],
        },
    )
    assert update_response.status_code == 200
    assert update_response.json()["enabled"] is False
    assert update_response.json()["description"] == "Updated description."
    assert update_response.json()["details"] == [{"title": "Output", "items": ["custom result"]}]

    delete_custom_response = client.delete(f"/api/registry/tools/{custom['id']}")
    assert delete_custom_response.status_code == 200
    assert delete_custom_response.json() is None

    delete_builtin_response = client.delete("/api/registry/tools/read_file")
    assert delete_builtin_response.status_code == 200
    assert delete_builtin_response.json()["id"] == "read_file"
    assert delete_builtin_response.json()["enabled"] is False
    tools_after_disable = client.get("/api/registry/tools").json()
    read_file = next(item for item in tools_after_disable if item["id"] == "read_file")
    assert read_file["builtin"] is True
    assert read_file["enabled"] is False
    assert read_file["details"]


def test_registry_skills_crud(monkeypatch: Any, tmp_path: Path) -> None:
    monkeypatch.setenv("CODEREADER_STATE_DIR", str(tmp_path / "state"))

    list_response = client.get("/api/registry/skills")
    assert list_response.status_code == 200
    skills = list_response.json()
    assert "VueSkill" in {item["id"] for item in skills}
    vue_skill = next(item for item in skills if item["id"] == "VueSkill")
    assert vue_skill["details"]
    assert {section["title"] for section in vue_skill["details"]} >= {"触发条件", "优先读取文件", "可用 tools"}

    create_response = client.post(
        "/api/registry/skills",
        json={
            "name": "CustomSkill",
            "description": "Custom skill.",
            "notes": "Only shown in local registry.",
            "details": [{"title": "Triggers", "items": ["manual"]}],
        },
    )
    assert create_response.status_code == 200
    custom = create_response.json()
    assert custom["details"] == [{"title": "Triggers", "items": ["manual"]}]

    update_response = client.patch(
        f"/api/registry/skills/{custom['id']}",
        json={"notes": "Updated notes.", "details": [{"title": "Outputs", "items": ["summary"]}]},
    )
    assert update_response.status_code == 200
    assert update_response.json()["notes"] == "Updated notes."
    assert update_response.json()["details"] == [{"title": "Outputs", "items": ["summary"]}]

    delete_response = client.delete(f"/api/registry/skills/{custom['id']}")
    assert delete_response.status_code == 200
    assert delete_response.json() is None


def test_registry_backfills_details_for_legacy_state(monkeypatch: Any, tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / "state.json").write_text(
        json.dumps(
            {
                "project_sessions": [],
                "tools": [
                    {
                        "id": "read_file",
                        "name": "Read File Custom Label",
                        "description": "Edited description.",
                        "notes": "Edited notes.",
                        "enabled": False,
                        "builtin": True,
                        "created_at": "2026-07-07T00:00:00Z",
                        "updated_at": "2026-07-07T00:00:00Z",
                    }
                ],
                "skills": [
                    {
                        "id": "VueSkill",
                        "name": "Vue Skill Custom Label",
                        "description": "Edited skill description.",
                        "notes": "Edited skill notes.",
                        "enabled": True,
                        "builtin": True,
                        "created_at": "2026-07-07T00:00:00Z",
                        "updated_at": "2026-07-07T00:00:00Z",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEREADER_STATE_DIR", str(state_dir))

    tools_response = client.get("/api/registry/tools")
    assert tools_response.status_code == 200
    read_file = next(item for item in tools_response.json() if item["id"] == "read_file")
    assert read_file["name"] == "Read File Custom Label"
    assert read_file["description"] == "Edited description."
    assert read_file["enabled"] is False
    assert read_file["details"]

    skills_response = client.get("/api/registry/skills")
    assert skills_response.status_code == 200
    vue_skill = next(item for item in skills_response.json() if item["id"] == "VueSkill")
    assert vue_skill["name"] == "Vue Skill Custom Label"
    assert vue_skill["description"] == "Edited skill description."
    assert vue_skill["details"]


def test_local_state_invalid_json_returns_clear_error(monkeypatch: Any, tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / "state.json").write_text("{not json", encoding="utf-8")
    monkeypatch.setenv("CODEREADER_STATE_DIR", str(state_dir))

    response = client.get("/api/projects/history")

    assert response.status_code == 500
    assert "invalid JSON" in response.json()["detail"]


def test_project_interpretation_api_returns_single_agent_result(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.ts").write_text("console.log('hello');\n", encoding="utf-8")
    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "name": "api-summary-sample",
                "scripts": {"dev": "vite", "build": "vite build"},
                "dependencies": {"vue": "^3.5.0"},
                "devDependencies": {"vite": "^5.4.0", "typescript": "^5.5.0"},
            }
        ),
        encoding="utf-8",
    )

    response = client.post(
        "/api/agent/project-interpretation",
        json={"project_path": str(tmp_path), "question": "怎么运行？"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["project_name"] == "api-summary-sample"
    assert payload["skill"] == "setup_analysis_skill"
    assert payload["prompt_version"] == "project_interpreter_v1"
    assert "npm run dev" in payload["setup_summary"]
    assert payload["prompt_messages"][0]["role"] == "system"
    assert "package.json" in {item["path"] for item in payload["evidence"]}
    assert payload["tool_calls"]
    assert "package.json" in payload["read_files"]


def test_agent_run_api_returns_fallback_without_llm_env(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setenv("CODEREADER_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.delenv("DASHSCOPE_BASE_URL", raising=False)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.ts").write_text("console.log('hello');\n", encoding="utf-8")
    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "name": "api-agent-sample",
                "scripts": {"dev": "vite"},
                "dependencies": {"vue": "^3.5.0"},
                "devDependencies": {"vite": "^5.4.0", "typescript": "^5.5.0"},
            }
        ),
        encoding="utf-8",
    )

    response = client.post(
        "/api/agent/run",
        json={"project_path": str(tmp_path), "question": "这个项目是干什么的？"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["project_name"] == "api-agent-sample"
    assert payload["fallback_used"] is True
    assert payload["used_llm"] is False
    assert payload["agent_steps"][0]["kind"] == "fallback"
    assert payload["task_id"].startswith("task-")
    assert "代码库理解报告" in payload["analysis_goal"]
    assert payload["analysis_plan"]
    assert "VueSkill" in payload["selected_skills"]
    assert payload["context_snapshot"]["evidence_count"] > 0
    assert payload["project_manual"]["title"] == "api-agent-sample 项目说明书"
    assert payload["project_manual"]["overview"]["one_liner"]
    assert payload["project_manual"]["technology_stack"]
    assert payload["project_manual"]["modules"]
    assert payload["project_manual"]["entrypoints"]
    assert payload["project_manual"]["directory_tree"]
    assert payload["project_manual"]["key_directories"]
    assert payload["project_memory"]["project_memory"]["positioning"]
    assert payload["project_memory"]["module_summaries"]
    assert payload["report"]["title"] == "api-agent-sample 项目解读报告"
    assert payload["report"]["module_summaries"]
    assert payload["trace_events"]
    assert any(event["stage"] == "Report Writer" for event in payload["trace_events"])


def test_agent_ask_api_returns_intent_answer_and_session_memory(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setenv("CODEREADER_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.delenv("DASHSCOPE_BASE_URL", raising=False)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.ts").write_text("console.log('hello');\n", encoding="utf-8")
    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "name": "api-ask-sample",
                "scripts": {"dev": "vite"},
                "dependencies": {"vue": "^3.5.0"},
                "devDependencies": {"vite": "^5.4.0", "typescript": "^5.5.0"},
            }
        ),
        encoding="utf-8",
    )

    run_response = client.post(
        "/api/agent/run",
        json={"project_path": str(tmp_path), "question": "生成项目说明书"},
    )
    assert run_response.status_code == 200

    ask_response = client.post(
        "/api/agent/ask",
        json={"project_path": str(tmp_path), "question": "项目用了哪些技术栈？"},
    )

    assert ask_response.status_code == 200
    payload = ask_response.json()
    assert payload["intent"] == "tech_stack"
    assert payload["answer"]
    assert payload["resolved_query"]["resolved_question"] == "项目用了哪些技术栈？"
    assert payload["intent_result"]["intent"] == "tech_stack"
    assert payload["tool_plan"]["need_tools"] is True
    assert payload["context_pack"]["project_context"]
    assert "code_evidence" in payload
    assert payload["tool_calls"]
    assert payload["tool_calls"][0]["reason"]
    assert payload["session_memory"]["turns"][-1]["intent"] == "tech_stack"
    assert payload["trace_events"]
    assert payload["used_llm"] is False
    assert payload["fallback_used"] is True
    assert payload["llm_model"] == "glm-5.1"


def test_agent_ask_stream_api_returns_sse_progress_and_final_payload(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setenv("CODEREADER_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.delenv("DASHSCOPE_BASE_URL", raising=False)
    write_minimal_java_project(tmp_path)

    response = client.post(
        "/api/agent/ask/stream",
        json={"project_path": str(tmp_path), "question": "UserController 是做什么的？"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    frames = [frame for frame in response.text.split("\n\n") if frame.strip()]
    assert any(frame.startswith("event: trace") for frame in frames)
    assert any(frame.startswith("event: tool_plan") for frame in frames)
    assert any(frame.startswith("event: tool_result") for frame in frames)
    assert frames[-1].startswith("event: final")
    data_line = next(line for line in frames[-1].splitlines() if line.startswith("data: "))
    payload = json.loads(data_line.removeprefix("data: "))
    assert payload["type"] == "final"
    assert payload["event"]["intent"] == "file_explanation"
    assert payload["event"]["answer"]


def test_agent_ask_conversations_keep_session_memory_isolated(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setenv("CODEREADER_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.delenv("DASHSCOPE_BASE_URL", raising=False)
    write_minimal_java_project(tmp_path)

    project_response = client.post(
        "/api/projects/history",
        json={"project_name": "demo-service", "project_path": str(tmp_path), "title": "demo-service"},
    )
    assert project_response.status_code == 200
    project_id = project_response.json()["id"]
    first_conversation = client.post(f"/api/projects/{project_id}/ask-conversations", json={"title": "登录流程"}).json()
    second_conversation = client.post(f"/api/projects/{project_id}/ask-conversations", json={"title": "配置位置"}).json()

    first_response = client.post(
        "/api/agent/ask/stream",
        json={"project_path": str(tmp_path), "question": "登录流程怎么走？", "conversation_id": first_conversation["id"]},
    )
    second_response = client.post(
        "/api/agent/ask/stream",
        json={"project_path": str(tmp_path), "question": "数据库配置在哪里？", "conversation_id": second_conversation["id"]},
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    conversations = client.get(f"/api/projects/{project_id}/ask-conversations").json()
    by_id = {item["id"]: item for item in conversations}
    assert [turn["intent"] for turn in by_id[first_conversation["id"]]["session_memory"]["turns"]] == ["flow_trace"]
    assert [turn["intent"] for turn in by_id[second_conversation["id"]]["session_memory"]["turns"]] == ["config_lookup"]
    assert len(by_id[first_conversation["id"]]["messages"]) == 2
    assert len(by_id[second_conversation["id"]]["messages"]) == 2


def test_agent_ask_stream_updates_only_target_conversation(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setenv("CODEREADER_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.delenv("DASHSCOPE_BASE_URL", raising=False)
    write_minimal_java_project(tmp_path)

    project_id = client.post(
        "/api/projects/history",
        json={"project_name": "demo-service", "project_path": str(tmp_path), "title": "demo-service"},
    ).json()["id"]
    target = client.post(f"/api/projects/{project_id}/ask-conversations", json={"title": "目标会话"}).json()
    untouched = client.post(f"/api/projects/{project_id}/ask-conversations", json={"title": "空会话"}).json()

    response = client.post(
        "/api/agent/ask/stream",
        json={"project_path": str(tmp_path), "question": "UserController 是做什么的？", "conversation_id": target["id"]},
    )

    assert response.status_code == 200
    final_payload = _final_sse_payload(response.text)
    assert final_payload["conversation"]["id"] == target["id"]
    conversations = client.get(f"/api/projects/{project_id}/ask-conversations").json()
    by_id = {item["id"]: item for item in conversations}
    assert by_id[target["id"]]["session_memory"]["turns"][-1]["intent"] == "file_explanation"
    assert by_id[untouched["id"]]["session_memory"]["turns"] == []
    assert "context_pack" not in by_id[target["id"]]
    assert "code_evidence" not in by_id[target["id"]]
    assert "tool_calls" not in by_id[target["id"]]


def test_agent_ask_stream_api_returns_error_event_for_invalid_path(tmp_path: Path) -> None:
    response = client.post(
        "/api/agent/ask/stream",
        json={"project_path": str(tmp_path / "missing"), "question": "项目是什么？"},
    )

    assert response.status_code == 200
    assert "event: error" in response.text
    assert "Project path does not exist" in response.text


def _final_sse_payload(text: str) -> dict[str, Any]:
    frames = [frame for frame in text.split("\n\n") if frame.strip()]
    final_frame = next(frame for frame in frames if frame.startswith("event: final"))
    data_line = next(line for line in final_frame.splitlines() if line.startswith("data: "))
    return json.loads(data_line.removeprefix("data: "))


def test_agent_run_stream_api_returns_sse_progress_and_project_manual(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setenv("CODEREADER_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.delenv("DASHSCOPE_BASE_URL", raising=False)
    write_vue_spring_monorepo(tmp_path)

    response = client.post(
        "/api/agent/run/stream",
        json={"project_path": str(tmp_path), "question": "生成项目说明书"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    frames = [frame for frame in response.text.split("\n\n") if frame.strip()]
    assert any(frame.startswith("event: step") for frame in frames)
    assert any(frame.startswith("event: trace") for frame in frames)
    assert frames[-1].startswith("event: final")
    data_line = next(line for line in frames[-1].splitlines() if line.startswith("data: "))
    payload = json.loads(data_line.removeprefix("data: "))
    assert payload["type"] == "final"
    manual = payload["event"]["project_manual"]
    assert manual["manual_overview"]["project_type"] == "前后端分离"
    assert "frontend/src/main.ts" in {entry["path"] for entry in manual["entrypoints"]}
    assert "backend/src/main/java/com/example/demo/DemoApplication.java" in {entry["path"] for entry in manual["entrypoints"]}


def test_model_settings_api_updates_model_and_reports_missing_env(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setenv("CODEREADER_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.delenv("DASHSCOPE_BASE_URL", raising=False)

    initial = client.get("/api/model-settings")

    assert initial.status_code == 200
    assert initial.json()["model"] == "glm-5.1"
    assert initial.json()["api_key_configured"] is False
    assert initial.json()["base_url_configured"] is False
    assert isinstance(initial.json()["litellm_installed"], bool)
    assert isinstance(initial.json()["langgraph_installed"], bool)

    updated = client.post("/api/model-settings", json={"model": "qwen-plus"})

    assert updated.status_code == 200
    assert updated.json()["model"] == "qwen-plus"

    test_response = client.post("/api/model-settings/test", json={})

    assert test_response.status_code == 200
    payload = test_response.json()
    assert payload["ok"] is False
    assert payload["model"] == "qwen-plus"
    assert set(payload["missing_environment"]) == {"DASHSCOPE_API_KEY", "DASHSCOPE_BASE_URL"}


def test_agent_run_api_returns_llm_result_with_mock(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setenv("CODEREADER_STATE_DIR", str(tmp_path / "state"))
    settings_response = client.post("/api/model-settings", json={"model": "qwen-plus"})
    assert settings_response.status_code == 200

    captured_manual_context: dict[str, Any] = {}

    def fake_run_agent_loop(
        project_path: str,
        question: str,
        max_steps: int = 6,
        *,
        max_context_chars: int = 24_000,
        max_tool_calls: int = 8,
        max_read_files: int = 4,
        llm_client: Any = None,
        project_manual_context: Any = None,
    ) -> AgentRunResult:
        captured_manual_context["value"] = project_manual_context
        captured_manual_context["budget"] = (max_context_chars, max_tool_calls, max_read_files)
        captured_manual_context["model"] = llm_client.config.model
        return AgentRunResult(
            project_name="mock-project",
            question=question,
            skill="project_overview_skill",
            final_answer="LLM answer",
            agent_steps=[AgentStep(index=1, kind="final", title="Final answer", summary="LLM answer")],
            used_llm=True,
            fallback_used=False,
        )

    monkeypatch.setattr(api_main, "run_agent_loop", fake_run_agent_loop)

    response = client.post(
        "/api/agent/run",
        json={
            "project_path": str(tmp_path),
            "question": "介绍项目",
            "max_context_chars": 12000,
            "max_tool_calls": 3,
            "max_read_files": 2,
            "project_manual_context": {
                "title": "mock-project 项目说明书",
                "overview": None,
                "technology_stack": [],
                "modules": [],
                "entrypoints": [],
                "directory_tree": [],
                "key_directories": [],
                "evidence": [],
                "uncertainties": [],
                "generated_by": "ProjectManualBuilder",
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["used_llm"] is True
    assert payload["fallback_used"] is False
    assert payload["final_answer"] == "LLM answer"
    assert captured_manual_context["value"].title == "mock-project 项目说明书"
    assert captured_manual_context["budget"] == (12000, 3, 2)
    assert captured_manual_context["model"] == "qwen-plus"
