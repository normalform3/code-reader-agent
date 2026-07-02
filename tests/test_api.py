from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

import apps.api.main as api_main
from apps.api.main import app
from code_reader_agent.github_importer import GitHubCloneError
from code_reader_agent.models import AgentRunResult, AgentStep, GitHubImportResult
from tests.test_scanner import write_minimal_java_project


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
    assert {module["id"] for module in payload["modules"]} >= {"controller", "service", "repository"}
    assert payload["controllers"] == ["src/main/java/com/example/demo/UserController.java"]
    assert "pom.xml" in {item["path"] for item in payload["evidence"]}
    assert any(item["excerpt"] for item in payload["evidence"] if item["path"] == "pom.xml")


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


def test_agent_run_api_returns_llm_result_with_mock(tmp_path: Path, monkeypatch: Any) -> None:
    def fake_run_agent_loop(project_path: str, question: str, max_steps: int = 6) -> AgentRunResult:
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
        json={"project_path": str(tmp_path), "question": "介绍项目"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["used_llm"] is True
    assert payload["fallback_used"] is False
    assert payload["final_answer"] == "LLM answer"
