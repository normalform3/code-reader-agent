from __future__ import annotations

from pathlib import Path

from code_reader_agent.interpreter import interpret_project
from code_reader_agent.prompts import PROJECT_INTERPRETER_PROMPT_VERSION
from tests.test_scanner import write_minimal_java_project, write_minimal_vue_project


def test_interpret_project_returns_prompt_and_grounded_summary(tmp_path: Path) -> None:
    write_minimal_vue_project(tmp_path)

    result = interpret_project(str(tmp_path), "这个项目是干什么的？")

    assert result.project_name == "sample-vue-app"
    assert result.skill == "project_overview_skill"
    assert result.prompt_version == PROJECT_INTERPRETER_PROMPT_VERSION
    assert [message.role for message in result.prompt_messages] == ["system", "user"]
    assert "Use only the provided scan context and evidence" in result.prompt_messages[0].content
    assert "sample-vue-app" in result.prompt_messages[1].content
    assert "Vue" in result.overview
    assert "pnpm run dev" in result.setup_summary
    assert [item.path for item in result.reading_path] == [
        "vite.config.ts",
        "src/main.ts",
        "src/App.vue",
        "src/router/index.ts",
    ]
    assert "package.json" in {item.path for item in result.evidence}
    assert result.warnings == []


def test_interpret_project_marks_missing_setup_evidence(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.ts").write_text("console.log('hello');\n", encoding="utf-8")

    result = interpret_project(str(tmp_path))

    assert "未在 package.json 中找到 scripts" in result.setup_summary
    assert "缺少 package.json" in " ".join(result.warnings)


def test_interpret_project_returns_java_onboarding_summary(tmp_path: Path) -> None:
    write_minimal_java_project(tmp_path)

    result = interpret_project(str(tmp_path), "这个 Java 项目怎么运行？")

    assert result.project_name == "demo-service"
    assert "Java" in result.overview
    assert "mvn spring-boot:run" in result.setup_summary
    assert "mvn test" in result.setup_summary
    assert "demo-service" in result.prompt_messages[1].content
    assert "java_build_tool: maven" in result.prompt_messages[1].content
    assert "pom.xml" in {item.path for item in result.evidence}
    assert [item.path for item in result.reading_path][:2] == [
        "src/main/resources/application.yml",
        "src/main/java/com/example/demo/DemoApplication.java",
    ]
    assert result.warnings == []
