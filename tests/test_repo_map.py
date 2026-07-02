from __future__ import annotations

from pathlib import Path

from code_reader_agent.repo_map.builder import build_repo_map
from code_reader_agent.scanner import scan_project
from tests.test_scanner import write_minimal_java_project, write_minimal_vue_project


def test_build_repo_map_for_vue_project(tmp_path: Path) -> None:
    write_minimal_vue_project(tmp_path)

    repo_map = build_repo_map(scan_project(tmp_path))

    assert repo_map.project_name == "sample-vue-app"
    assert repo_map.package_manager == "pnpm"
    assert {module.id for module in repo_map.modules} >= {"app", "router", "components", "config"}
    assert "src/router/index.ts" in repo_map.routes
    assert "src/App.vue" in repo_map.components
    assert "package.json" in {item.path for item in repo_map.evidence}


def test_build_repo_map_for_java_project(tmp_path: Path) -> None:
    write_minimal_java_project(tmp_path)

    repo_map = build_repo_map(scan_project(tmp_path))

    assert repo_map.project_name == "demo-service"
    assert repo_map.java_build_tool == "maven"
    assert {module.id for module in repo_map.modules} >= {"app", "config", "controller", "service", "repository"}
    assert repo_map.controllers == ["src/main/java/com/example/demo/UserController.java"]
    assert repo_map.services == ["src/main/java/com/example/demo/UserService.java"]
    assert repo_map.repositories == ["src/main/java/com/example/demo/UserRepository.java"]
    assert "src/main/java/com/example/demo/UserController.java" in repo_map.api_endpoints
    assert "pom.xml" in {item.path for item in repo_map.evidence}
