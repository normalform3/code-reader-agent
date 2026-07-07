from __future__ import annotations

import json
from pathlib import Path

import pytest

from code_reader_agent.scanner import ProjectScanError, scan_project


def write_minimal_vue_project(root: Path) -> None:
    (root / "src" / "router").mkdir(parents=True)
    (root / "node_modules" / "ignored-package").mkdir(parents=True)
    (root / "src" / "main.ts").write_text("import { createApp } from 'vue';\n", encoding="utf-8")
    (root / "src" / "App.vue").write_text("<template><main /></template>\n", encoding="utf-8")
    (root / "src" / "router" / "index.ts").write_text("import { createRouter } from 'vue-router';\n", encoding="utf-8")
    (root / "vite.config.ts").write_text("import { defineConfig } from 'vite';\n", encoding="utf-8")
    (root / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    (root / "package.json").write_text(
        json.dumps(
            {
                "name": "sample-vue-app",
                "version": "0.1.0",
                "scripts": {
                    "dev": "vite",
                    "build": "vue-tsc && vite build",
                },
                "dependencies": {
                    "vue": "^3.5.0",
                    "pinia": "^2.2.0",
                    "vue-router": "^4.4.0",
                    "axios": "^1.7.0",
                    "element-plus": "^2.8.0",
                },
                "devDependencies": {
                    "vite": "^5.4.0",
                    "typescript": "^5.5.0",
                },
            }
        ),
        encoding="utf-8",
    )


def write_minimal_java_project(root: Path) -> None:
    (root / "src" / "main" / "java" / "com" / "example" / "demo").mkdir(parents=True)
    (root / "src" / "main" / "resources").mkdir(parents=True)
    (root / "src" / "main" / "java" / "com" / "example" / "demo" / "DemoApplication.java").write_text(
        "package com.example.demo;\n\n"
        "import org.springframework.boot.autoconfigure.SpringBootApplication;\n\n"
        "@SpringBootApplication\n"
        "public class DemoApplication {}\n",
        encoding="utf-8",
    )
    (root / "src" / "main" / "java" / "com" / "example" / "demo" / "UserController.java").write_text(
        "package com.example.demo;\n\n"
        "import org.springframework.web.bind.annotation.RestController;\n\n"
        "@RestController\n"
        "public class UserController {}\n",
        encoding="utf-8",
    )
    (root / "src" / "main" / "java" / "com" / "example" / "demo" / "UserService.java").write_text(
        "package com.example.demo;\n\n"
        "import org.springframework.stereotype.Service;\n\n"
        "@Service\n"
        "public class UserService {}\n",
        encoding="utf-8",
    )
    (root / "src" / "main" / "java" / "com" / "example" / "demo" / "UserRepository.java").write_text(
        "package com.example.demo;\n\n"
        "import org.springframework.stereotype.Repository;\n\n"
        "@Repository\n"
        "public class UserRepository {}\n",
        encoding="utf-8",
    )
    (root / "src" / "main" / "resources" / "application.yml").write_text(
        "spring:\n  application:\n    name: demo-service\n",
        encoding="utf-8",
    )
    (root / "pom.xml").write_text(
        """<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example</groupId>
  <artifactId>demo-service</artifactId>
  <version>0.1.0</version>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
      <groupId>org.mybatis.spring.boot</groupId>
      <artifactId>mybatis-spring-boot-starter</artifactId>
      <version>3.0.3</version>
    </dependency>
  </dependencies>
</project>
""",
        encoding="utf-8",
    )


def test_scan_minimal_vue_vite_project(tmp_path: Path) -> None:
    write_minimal_vue_project(tmp_path)

    result = scan_project(tmp_path)

    assert result.project_name == "sample-vue-app"
    assert result.package.found is True
    assert result.package.package_manager == "pnpm"
    assert result.package.scripts["dev"] == "vite"
    assert result.package.dependencies["vue"] == "^3.5.0"
    assert result.package.dev_dependencies["typescript"] == "^5.5.0"

    stack_names = {tag.name for tag in result.detected_stack}
    assert {"Vue", "Vite", "TypeScript", "Pinia", "Vue Router", "Axios", "Element Plus"} <= stack_names

    entrypoint_paths = {entry.path for entry in result.entrypoints}
    assert {"src/main.ts", "src/App.vue", "src/router/index.ts", "vite.config.ts"} <= entrypoint_paths

    tree_paths = {entry.path for entry in result.file_tree}
    assert "src/main.ts" in tree_paths
    assert "node_modules" not in tree_paths
    assert "node_modules/ignored-package" not in tree_paths
    assert result.warnings == []


def test_scan_minimal_java_maven_project(tmp_path: Path) -> None:
    write_minimal_java_project(tmp_path)

    result = scan_project(tmp_path)

    assert result.project_name == "demo-service"
    assert result.package.found is False
    assert result.java_build.found is True
    assert result.java_build.build_tool == "maven"
    assert result.java_build.group_id == "com.example"
    assert result.java_build.artifact_id == "demo-service"
    assert result.java_build.version == "0.1.0"
    assert result.java_build.dependencies["spring-boot-starter-web"] is None
    assert result.java_build.dependencies["mybatis-spring-boot-starter"] == "3.0.3"
    assert result.java_build.config_files == ["src/main/resources/application.yml"]

    stack_names = {tag.name for tag in result.detected_stack}
    assert {"Java", "Maven", "Spring Web", "Spring Security", "MyBatis"} <= stack_names

    entrypoint_kinds = {entry.kind for entry in result.entrypoints}
    assert {"java_app_entry", "java_controller", "java_service", "java_repository", "java_config"} <= entrypoint_kinds
    assert result.warnings == []


def test_scan_without_package_json_returns_warning(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.ts").write_text("console.log('hello');\n", encoding="utf-8")

    result = scan_project(tmp_path)

    assert result.package.found is False
    assert result.package.scripts == {}
    assert result.package.dependencies == {}
    assert result.warnings == [
        "package.json not found; package metadata and dependency-based stack detection are unavailable."
    ]


def test_scan_missing_path_raises_clear_error(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing"

    with pytest.raises(ProjectScanError, match="Project path does not exist"):
        scan_project(missing_path)


def test_scan_file_path_raises_clear_error(tmp_path: Path) -> None:
    file_path = tmp_path / "package.json"
    file_path.write_text("{}", encoding="utf-8")

    with pytest.raises(ProjectScanError, match="Project path is not a directory"):
        scan_project(file_path)


def test_scan_ignores_node_modules(tmp_path: Path) -> None:
    (tmp_path / "node_modules" / "vue").mkdir(parents=True)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "App.vue").write_text("<template />\n", encoding="utf-8")

    result = scan_project(tmp_path)

    assert all(not entry.path.startswith("node_modules") for entry in result.file_tree)


def test_scan_detects_extended_python_and_deployment_stack(tmp_path: Path) -> None:
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.py").write_text("from fastapi import FastAPI\n", encoding="utf-8")
    (tmp_path / "Dockerfile").write_text("FROM python:3.12\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        """[project]
name = "python-agent"
dependencies = ["fastapi>=0.115", "langgraph>=0.2", "pytest>=8"]
""",
        encoding="utf-8",
    )

    result = scan_project(tmp_path)

    stack_names = {tag.name for tag in result.detected_stack}
    assert {"FastAPI", "LangGraph", "Pytest", "Docker"} <= stack_names
