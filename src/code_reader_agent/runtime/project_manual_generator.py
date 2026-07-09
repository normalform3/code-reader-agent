"""Dedicated structured LLM flow for the MVP project manual."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import ValidationError

from code_reader_agent.models import (
    AgentStep,
    ProjectManual,
    ProjectManualCoreModule,
    ProjectManualOverview,
    ProjectManualRepoMapItem,
    ProjectSummary,
    RepoMap,
)
from code_reader_agent.runtime.analysis import build_project_manual
from code_reader_agent.runtime.llm_client import LLMConfigurationError, LiteLLMClient


MAX_MANUAL_MODULES = 8
MIN_MANUAL_MODULES = 5

MANUAL_SYSTEM_PROMPT = """You are CodeReader Agent's dedicated project manual writer.

Your job is to generate a concise first-pass project manual for a developer who
just imported an unfamiliar repository. This is not Ask mode and not a full
architecture report.

Return JSON only with this shape:
{
  "overview": {
    "project_name": "...",
    "project_type": "前端 | 后端 | 前后端分离 | 工具库 / CLI | 多模块项目 | 待确认项目",
    "one_liner": "...",
    "main_stack": ["..."],
    "build_tools": ["..."],
    "entrypoints": ["..."],
    "maturity_observations": ["..."]
  },
  "repo_map": [
    {"path": "...", "role": "...", "reason": "...", "importance": "core | supporting | skippable"}
  ],
  "modules": [
    {
      "id": "...",
      "name": "...",
      "responsibility": "...",
      "related_files": ["..."],
      "api_candidates": ["..."],
      "identification_basis": "...",
      "confidence": 0.8
    }
  ],
  "warnings": ["..."]
}

Use only provided candidate module ids, directory paths, entrypoint paths, API
candidates, and file paths. Do not invent files, directories, APIs, database
tables, dependencies, or runtime behavior. Prefer 5-8 high-value modules when
there are enough candidates. Prioritize auth/login, user management,
permissions, configuration, file upload, core business modules, statistics, and
system management when the candidates support them.
"""


class ProjectManualLLMClient(Protocol):
    """Protocol for tests and the production LiteLLM adapter."""

    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> Any:
        """Return an OpenAI-compatible chat completion object or dictionary."""


@dataclass(frozen=True)
class ProjectManualGenerationResult:
    """Result from the dedicated project manual generation flow."""

    project_manual: ProjectManual
    warnings: list[str]
    agent_steps: list[AgentStep]
    used_llm: bool
    fallback_used: bool
    fallback_reason: str | None = None
    llm_model: str | None = None


def generate_project_manual(
    *,
    project_path: str,
    repo_map: RepoMap,
    llm_client: ProjectManualLLMClient | None = None,
) -> ProjectManualGenerationResult:
    """Generate the MVP project manual with a dedicated structured LLM call."""

    fallback_manual = build_project_manual(repo_map, generated_by="ProjectManualBuilder (deterministic fallback)")
    client = llm_client or LiteLLMClient()
    llm_model = client.config.model if isinstance(client, LiteLLMClient) else None
    if llm_client is None and isinstance(client, LiteLLMClient) and not client.is_configured():
        missing_envs = " or ".join(client.missing_environment_variables())
        return _fallback_result(fallback_manual, f"Missing {missing_envs}; deterministic project manual was used.", llm_model)

    prompt_payload = _manual_prompt_payload(project_path, repo_map, fallback_manual)
    messages = [
        {"role": "system", "content": MANUAL_SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(prompt_payload, ensure_ascii=False)},
    ]
    try:
        response = client.complete(messages, [])
    except (LLMConfigurationError, Exception) as exc:
        return _fallback_result(fallback_manual, f"Project manual LLM generation failed: {exc}", llm_model)

    content = _message_content(_extract_message(response))
    parsed = _parse_final_json(content)
    if parsed is None:
        return _fallback_result(fallback_manual, "Project manual LLM response was not valid JSON.", llm_model)

    manual, validation_warnings = _apply_structured_manual(fallback_manual, repo_map, parsed)
    used_llm = manual.generated_by == "ProjectManualLLMGenerator + ProjectManualBuilder"
    agent_steps = [
        AgentStep(
            index=1,
            kind="llm" if used_llm else "fallback",
            title="Project manual structured generation",
            summary="Generated MVP project manual with dedicated LLM flow."
            if used_llm
            else "Project manual LLM output was ignored; deterministic fallback was used.",
            status="success" if used_llm else "error",
        )
    ]
    return ProjectManualGenerationResult(
        project_manual=manual,
        warnings=validation_warnings,
        agent_steps=agent_steps,
        used_llm=used_llm,
        fallback_used=not used_llm,
        fallback_reason=_first_warning(validation_warnings) if not used_llm else None,
        llm_model=llm_model,
    )


def _fallback_result(manual: ProjectManual, warning: str, llm_model: str | None) -> ProjectManualGenerationResult:
    manual.uncertainties = _dedupe_strings([*manual.uncertainties, warning])
    return ProjectManualGenerationResult(
        project_manual=manual,
        warnings=[warning],
        agent_steps=[
            AgentStep(
                index=1,
                kind="fallback",
                title="Project manual deterministic fallback",
                summary=warning,
                status="success",
            )
        ],
        used_llm=False,
        fallback_used=True,
        fallback_reason=warning,
        llm_model=llm_model,
    )


def _manual_prompt_payload(project_path: str, repo_map: RepoMap, fallback_manual: ProjectManual) -> dict[str, Any]:
    allowed_files = _allowed_files(repo_map)
    return {
        "project_path": project_path,
        "project_name": repo_map.project_name,
        "deterministic_overview": fallback_manual.manual_overview.model_dump() if fallback_manual.manual_overview else None,
        "stack": [item.model_dump() for item in repo_map.stack_explanations[:10]],
        "build_tools": {
            "package_manager": repo_map.package_manager,
            "java_build_tool": repo_map.java_build_tool,
            "run_scripts": repo_map.run_scripts,
        },
        "entrypoint_candidates": [entry.model_dump() for entry in repo_map.entrypoints[:10]],
        "directory_candidates": [item.model_dump() for item in fallback_manual.repo_map[:10]],
        "module_candidates": [
            {
                "id": module.id,
                "name": module.name,
                "type": module.type,
                "current_responsibility": module.responsibility,
                "related_files": module.related_files,
                "api_candidates": module.api_candidates,
                "identification_basis": module.identification_basis,
                "confidence": module.confidence,
            }
            for module in fallback_manual.modules[:MAX_MANUAL_MODULES]
        ],
        "allowed_file_paths": sorted(allowed_files)[:120],
        "allowed_api_candidates": _allowed_api_candidates(repo_map),
        "evidence_paths": [item.path for item in repo_map.evidence[:12]],
    }


def _apply_structured_manual(
    fallback_manual: ProjectManual,
    repo_map: RepoMap,
    parsed: dict[str, Any],
) -> tuple[ProjectManual, list[str]]:
    warnings = _string_list(parsed.get("warnings"))
    manual = fallback_manual.model_copy(deep=True)
    allowed_directories = {item.path for item in manual.repo_map}
    allowed_modules = {module.id: module for module in manual.modules}
    allowed_files = _allowed_files(repo_map)
    allowed_apis = set(_allowed_api_candidates(repo_map))

    overview = _parse_overview(parsed.get("overview"), manual)
    if overview is None:
        warnings.append("LLM overview was invalid; deterministic overview was used.")
    else:
        manual.manual_overview = overview
        manual.overview = ProjectSummary(
            one_liner=overview.one_liner,
            audience="面向首次阅读该仓库的开发者。",
            problem="帮助用户快速判断项目类型、技术栈、入口和阅读方向。",
            confidence=0.75,
            evidence=overview.entrypoints[:4],
        )

    repo_map_items = _parse_repo_map_items(parsed.get("repo_map"), allowed_directories, warnings)
    if repo_map_items is None:
        warnings.append("LLM repo_map was invalid; deterministic key directories were used.")
    elif repo_map_items:
        manual.repo_map = repo_map_items[:10]
        directory_by_path = {directory.path: directory for directory in manual.key_directories}
        for item in manual.repo_map:
            directory = directory_by_path.get(item.path)
            if directory:
                directory.role = item.role
                directory.reason = item.reason
                directory.importance = item.importance

    core_modules = _parse_core_modules(parsed.get("modules"), allowed_modules, allowed_files, allowed_apis, warnings)
    if core_modules is None:
        warnings.append("LLM modules were invalid; deterministic module cards were used.")
    elif core_modules:
        manual.core_modules = core_modules[:MAX_MANUAL_MODULES]
        modules_by_id = {module.id: module for module in manual.modules}
        for item in manual.core_modules:
            module = modules_by_id.get(item.id)
            if module:
                module.name = item.name
                module.responsibility = item.responsibility
                module.related_files = item.related_files
                module.api_candidates = item.api_candidates
                module.identification_basis = item.identification_basis
                module.confidence = item.confidence

    if overview or repo_map_items or core_modules:
        manual.generated_by = "ProjectManualLLMGenerator + ProjectManualBuilder"
    if warnings:
        manual.uncertainties = _dedupe_strings([*manual.uncertainties, *warnings])
    return manual, _dedupe_strings(warnings)


def _parse_overview(raw_overview: Any, fallback_manual: ProjectManual) -> ProjectManualOverview | None:
    if not isinstance(raw_overview, dict):
        return None
    fallback = fallback_manual.manual_overview
    payload = {
        "project_name": str(raw_overview.get("project_name") or (fallback.project_name if fallback else "")),
        "project_type": str(raw_overview.get("project_type") or (fallback.project_type if fallback else "待确认项目")),
        "one_liner": str(raw_overview.get("one_liner") or "").strip(),
        "main_stack": _string_list(raw_overview.get("main_stack")),
        "build_tools": _string_list(raw_overview.get("build_tools")),
        "entrypoints": _string_list(raw_overview.get("entrypoints")),
        "maturity_observations": _string_list(raw_overview.get("maturity_observations")),
    }
    if not payload["one_liner"]:
        return None
    try:
        return ProjectManualOverview.model_validate(payload)
    except ValidationError:
        return None


def _parse_repo_map_items(
    raw_items: Any,
    allowed_directories: set[str],
    warnings: list[str],
) -> list[ProjectManualRepoMapItem] | None:
    if raw_items is None:
        return []
    if not isinstance(raw_items, list):
        return None
    parsed: list[ProjectManualRepoMapItem] = []
    for item in raw_items:
        if not isinstance(item, dict):
            return None
        path = str(item.get("path") or "").strip()
        if path not in allowed_directories:
            warnings.append(f"LLM repo_map referenced unknown directory path: {path}.")
            continue
        try:
            parsed.append(
                ProjectManualRepoMapItem.model_validate(
                    {
                        "path": path,
                        "role": str(item.get("role") or "").strip(),
                        "reason": str(item.get("reason") or "").strip(),
                        "importance": str(item.get("importance") or "supporting"),
                    }
                )
            )
        except ValidationError:
            continue
    return parsed


def _parse_core_modules(
    raw_modules: Any,
    allowed_modules: dict[str, Any],
    allowed_files: set[str],
    allowed_apis: set[str],
    warnings: list[str],
) -> list[ProjectManualCoreModule] | None:
    if raw_modules is None:
        return []
    if not isinstance(raw_modules, list):
        return None
    parsed: list[ProjectManualCoreModule] = []
    for item in raw_modules:
        if not isinstance(item, dict):
            return None
        module_id = str(item.get("id") or "").strip()
        fallback = allowed_modules.get(module_id)
        if fallback is None:
            warnings.append(f"LLM module referenced unknown module id: {module_id}.")
            continue
        related_files = [path for path in _string_list(item.get("related_files")) if path in allowed_files]
        dropped_files = [path for path in _string_list(item.get("related_files")) if path not in allowed_files]
        warnings.extend(f"LLM module {module_id} referenced unknown file path: {path}." for path in dropped_files)
        api_candidates = [api for api in _string_list(item.get("api_candidates")) if api in allowed_apis]
        try:
            parsed.append(
                ProjectManualCoreModule.model_validate(
                    {
                        "id": module_id,
                        "name": str(item.get("name") or fallback.name).strip(),
                        "responsibility": str(item.get("responsibility") or fallback.responsibility).strip(),
                        "related_files": related_files or fallback.related_files,
                        "api_candidates": api_candidates,
                        "identification_basis": str(item.get("identification_basis") or fallback.identification_basis).strip(),
                        "confidence": item.get("confidence") if isinstance(item.get("confidence"), int | float) else fallback.confidence,
                    }
                )
            )
        except ValidationError:
            continue
    return parsed[:MAX_MANUAL_MODULES]


def _allowed_files(repo_map: RepoMap) -> set[str]:
    paths = {item.path for item in repo_map.files}
    paths.update(entry.path for entry in repo_map.entrypoints if entry.exists)
    paths.update(item.path for item in repo_map.evidence)
    paths.update(path for module in repo_map.modules for path in [*module.key_files, *module.entry_files])
    return paths


def _allowed_api_candidates(repo_map: RepoMap) -> list[str]:
    return _dedupe_strings([*repo_map.api_endpoints, *repo_map.api_flows, *repo_map.auth_flows])


def _extract_message(response: Any) -> Any:
    if isinstance(response, dict):
        return response["choices"][0]["message"]
    return response.choices[0].message


def _message_content(message: Any) -> str:
    if isinstance(message, dict):
        return str(message.get("content") or "")
    return str(getattr(message, "content", "") or "")


def _parse_final_json(content: str) -> dict[str, Any] | None:
    stripped = _extract_json_object(content.strip())
    if stripped is None:
        return None
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.startswith("json"):
            stripped = stripped[4:].strip()
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _extract_json_object(content: str) -> str | None:
    if not content:
        return None
    stripped = content.strip()
    if stripped.startswith("```") or stripped.startswith("{"):
        return stripped
    start = stripped.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escaped = False
    for index, char in enumerate(stripped[start:], start=start):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return stripped[start : index + 1]
    return None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if isinstance(item, str) and item.strip()]


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique


def _first_warning(warnings: list[str]) -> str | None:
    for warning in warnings:
        if warning:
            return warning
    return None
