from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from code_reader_agent.repo_map.builder import build_repo_map
from code_reader_agent.runtime.project_manual_generator import generate_project_manual
from code_reader_agent.scanner import scan_project
from tests.test_scanner import write_minimal_java_project


class FakeLLMClient:
    def __init__(self, response: dict[str, Any] | None = None, error: Exception | None = None) -> None:
        self.response = response or {}
        self.error = error
        self.messages: list[dict[str, Any]] = []

    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
        self.messages = messages
        if self.error:
            raise self.error
        return {"choices": [{"message": {"role": "assistant", "content": json.dumps(self.response, ensure_ascii=False)}}]}


class TextLLMClient:
    def __init__(self, content: str) -> None:
        self.content = content

    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
        return {"choices": [{"message": {"role": "assistant", "content": self.content}}]}


def _repo_map(path: Path):
    return build_repo_map(scan_project(path))


def test_project_manual_generator_applies_valid_structured_manual(tmp_path: Path) -> None:
    write_minimal_java_project(tmp_path)
    controller_path = "src/main/java/com/example/demo/UserController.java"
    client = FakeLLMClient(
        {
            "overview": {
                "project_name": "demo-service",
                "project_type": "后端",
                "one_liner": "这是一个面向用户资源的 Spring Boot 后端服务。",
                "main_stack": ["Spring Boot", "MyBatis"],
                "build_tools": ["Maven"],
                "entrypoints": ["src/main/java/com/example/demo/DemoApplication.java"],
                "maturity_observations": ["包含 Maven 构建配置"],
            },
            "repo_map": [{"path": "src", "role": "后端源码根目录", "reason": "包含 Java 源码和资源。", "importance": "core"}],
            "modules": [
                {
                    "id": "controller",
                    "name": "用户接口模块",
                    "responsibility": "接收用户相关 HTTP 请求。",
                    "related_files": [controller_path],
                    "api_candidates": [],
                    "identification_basis": "根据 UserController.java 识别。",
                    "confidence": 0.9,
                }
            ],
            "warnings": [],
        }
    )

    result = generate_project_manual(project_path=str(tmp_path), repo_map=_repo_map(tmp_path), llm_client=client)

    assert result.used_llm is True
    assert result.project_manual.manual_overview
    assert result.project_manual.manual_overview.project_type == "后端"
    assert result.project_manual.repo_map[0].role == "后端源码根目录"
    assert result.project_manual.core_modules[0].related_files == [controller_path]


def test_project_manual_generator_filters_invalid_references(tmp_path: Path) -> None:
    write_minimal_java_project(tmp_path)
    client = FakeLLMClient(
        {
            "overview": {
                "project_name": "demo-service",
                "project_type": "后端",
                "one_liner": "这是一个 Spring Boot 服务。",
                "main_stack": ["Spring Boot"],
                "build_tools": ["Maven"],
                "entrypoints": [],
                "maturity_observations": [],
            },
            "repo_map": [{"path": "missing", "role": "虚构目录", "reason": "不应该出现。"}],
            "modules": [
                {"id": "missing-module", "responsibility": "不应该出现。"},
                {"id": "controller", "responsibility": "合法模块。", "related_files": ["missing/File.java"]},
            ],
            "warnings": [],
        }
    )

    result = generate_project_manual(project_path=str(tmp_path), repo_map=_repo_map(tmp_path), llm_client=client)

    assert all(item.path != "missing" for item in result.project_manual.repo_map)
    assert any("unknown directory path: missing" in warning for warning in result.warnings)
    assert any("unknown module id: missing-module" in warning for warning in result.warnings)
    assert any("unknown file path: missing/File.java" in warning for warning in result.warnings)


def test_project_manual_generator_extracts_json_from_text_response(tmp_path: Path) -> None:
    write_minimal_java_project(tmp_path)
    payload = {
        "overview": {
            "project_name": "demo-service",
            "project_type": "后端",
            "one_liner": "这是模型生成的项目说明书总览。",
            "main_stack": ["Spring Boot"],
            "build_tools": ["Maven"],
            "entrypoints": [],
            "maturity_observations": [],
        },
        "repo_map": [],
        "modules": [],
        "warnings": [],
    }
    client = TextLLMClient(f"下面是 JSON：\n{json.dumps(payload, ensure_ascii=False)}\n请使用。")

    result = generate_project_manual(project_path=str(tmp_path), repo_map=_repo_map(tmp_path), llm_client=client)

    assert result.used_llm is True
    assert result.project_manual.manual_overview
    assert result.project_manual.manual_overview.one_liner == "这是模型生成的项目说明书总览。"


def test_project_manual_generator_limits_modules_to_top_eight(tmp_path: Path) -> None:
    write_minimal_java_project(tmp_path)
    modules = [
        {
            "id": "controller",
            "name": f"模块 {index}",
            "responsibility": f"职责 {index}",
            "related_files": ["src/main/java/com/example/demo/UserController.java"],
            "confidence": 0.8,
        }
        for index in range(10)
    ]
    client = FakeLLMClient(
        {
            "overview": {
                "project_name": "demo-service",
                "project_type": "后端",
                "one_liner": "这是一个 Spring Boot 服务。",
                "main_stack": ["Spring Boot"],
                "build_tools": ["Maven"],
                "entrypoints": [],
                "maturity_observations": [],
            },
            "repo_map": [],
            "modules": modules,
            "warnings": [],
        }
    )

    result = generate_project_manual(project_path=str(tmp_path), repo_map=_repo_map(tmp_path), llm_client=client)

    assert len(result.project_manual.core_modules) <= 8


def test_project_manual_generator_uses_fallback_on_llm_failure(tmp_path: Path) -> None:
    write_minimal_java_project(tmp_path)

    result = generate_project_manual(
        project_path=str(tmp_path),
        repo_map=_repo_map(tmp_path),
        llm_client=FakeLLMClient(error=RuntimeError("offline")),
    )

    assert result.used_llm is False
    assert result.fallback_used is True
    assert result.fallback_reason == "Project manual LLM generation failed: offline"
    assert result.project_manual.manual_overview
    assert result.project_manual.core_modules
