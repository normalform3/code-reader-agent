from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from apps.api.main import app
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


def test_scan_project_api_returns_clear_error_for_invalid_path(tmp_path: Path) -> None:
    response = client.post("/api/projects/scan", json={"project_path": str(tmp_path / "missing")})

    assert response.status_code == 400
    assert "Project path does not exist" in response.json()["detail"]


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
    assert payload["skill"] == "project_overview_skill"
    assert payload["prompt_version"] == "project_interpreter_v1"
    assert "npm run dev" in payload["setup_summary"]
    assert payload["prompt_messages"][0]["role"] == "system"
    assert "package.json" in {item["path"] for item in payload["evidence"]}
