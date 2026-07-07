from __future__ import annotations

from pathlib import Path

from code_reader_agent.repo_map.builder import build_repo_map
from code_reader_agent.scanner import scan_project
from tests.test_scanner import write_minimal_java_project, write_minimal_vue_project


def test_build_repo_map_for_vue_project(tmp_path: Path) -> None:
    write_minimal_vue_project(tmp_path)
    (tmp_path / "README.md").write_text("# Sample Vue App\n\nA dashboard for repository onboarding.\n", encoding="utf-8")

    repo_map = build_repo_map(scan_project(tmp_path))

    assert repo_map.project_name == "sample-vue-app"
    assert repo_map.project_summary is not None
    assert "Sample Vue App" in repo_map.project_summary.one_liner
    assert repo_map.package_manager == "pnpm"
    assert {module.id for module in repo_map.modules} >= {"app", "router", "components", "config"}
    assert all(module.reading_priority > 0 for module in repo_map.modules)
    assert "src/router/index.ts" in repo_map.routes
    assert "src/App.vue" in repo_map.components
    assert "package.json" in {item.path for item in repo_map.evidence}
    assert "README.md" in {item.path for item in repo_map.evidence}
    assert any(item.name == "Vue" and "前端" in item.category for item in repo_map.stack_explanations)
    assert any(item.path == "src" and item.importance == "core" for item in repo_map.directory_insights)
    assert any(item.action == "read_first" and item.path == "src/main.ts" for item in repo_map.reading_recommendations)


def test_build_repo_map_for_java_project(tmp_path: Path) -> None:
    write_minimal_java_project(tmp_path)

    repo_map = build_repo_map(scan_project(tmp_path))

    assert repo_map.project_name == "demo-service"
    assert repo_map.project_summary is not None
    assert "Java" in repo_map.project_summary.one_liner
    assert repo_map.java_build_tool == "maven"
    assert {module.id for module in repo_map.modules} >= {"app", "config", "controller", "service", "repository"}
    assert repo_map.controllers == ["src/main/java/com/example/demo/UserController.java"]
    assert repo_map.services == ["src/main/java/com/example/demo/UserService.java"]
    assert repo_map.repositories == ["src/main/java/com/example/demo/UserRepository.java"]
    assert "src/main/java/com/example/demo/UserController.java" in repo_map.api_endpoints
    assert "pom.xml" in {item.path for item in repo_map.evidence}
    assert any(item.name == "Maven" and item.category == "构建工具" for item in repo_map.stack_explanations)
    assert any(item.action == "read_first" and item.path.endswith("DemoApplication.java") for item in repo_map.reading_recommendations)


def test_build_repo_map_without_readme_returns_low_confidence_summary(tmp_path: Path) -> None:
    write_minimal_vue_project(tmp_path)

    repo_map = build_repo_map(scan_project(tmp_path))

    assert repo_map.project_summary is not None
    assert repo_map.project_summary.confidence < 0.6
    assert "缺少 README" in repo_map.project_summary.problem
