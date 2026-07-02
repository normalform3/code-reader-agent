"""Deterministic Repo Map builder for Phase 2."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import PurePosixPath

from code_reader_agent.models import (
    FileTreeEntry,
    ProjectScanResult,
    RepoMap,
    RepoMapEvidence,
    RepoMapFile,
    RepoMapModule,
)


MODULE_DEFINITIONS = {
    "app": ("Application", "app", "Application bootstrap and top-level runtime wiring."),
    "router": ("Router", "router", "Frontend route definitions and navigation structure."),
    "store": ("State Store", "store", "Frontend state management and shared client state."),
    "api": ("API Client", "api", "Frontend API modules and request wrappers."),
    "views": ("Views", "views", "Routed pages and screen-level components."),
    "components": ("Components", "components", "Reusable UI components."),
    "config": ("Configuration", "config", "Build, runtime, and application configuration."),
    "controller": ("Controllers", "controller", "Java HTTP entrypoints and request handlers."),
    "service": ("Services", "service", "Java business logic boundaries."),
    "repository": ("Repositories", "repository", "Java data access boundaries."),
    "test": ("Tests", "test", "Project tests and validation fixtures."),
}


def build_repo_map(scan: ProjectScanResult) -> RepoMap:
    """Build a deterministic Repo Map from a scan result."""

    evidence = _build_evidence(scan)
    evidence_by_path = {item.path: item.id for item in evidence}
    repo_files = [_build_repo_file(entry, evidence_by_path) for entry in scan.file_tree if entry.kind == "file"]
    modules = _build_modules(repo_files)

    return RepoMap(
        project_name=scan.project_name,
        project_path=scan.project_path,
        detected_stack=scan.detected_stack,
        package_manager=scan.package.package_manager,
        java_build_tool=scan.java_build.build_tool,
        run_scripts=scan.package.scripts,
        entrypoints=scan.entrypoints,
        modules=modules,
        files=repo_files,
        dependencies={**scan.package.dependencies, **scan.package.dev_dependencies, **scan.java_build.dependencies},
        routes=[item.path for item in repo_files if item.role == "router"],
        api_endpoints=[item.path for item in repo_files if item.role in {"api_client", "controller"}],
        api_flows=_candidate_flow_paths(repo_files, {"api_client", "controller", "service", "repository"}),
        auth_flows=_candidate_auth_paths(repo_files),
        stores=[item.path for item in repo_files if item.role == "store"],
        java_packages=sorted(_java_packages(repo_files)),
        controllers=[item.path for item in repo_files if item.role == "controller"],
        services=[item.path for item in repo_files if item.role == "service"],
        repositories=[item.path for item in repo_files if item.role == "repository"],
        components=[item.path for item in repo_files if item.role == "component"],
        evidence=evidence,
        warnings=scan.warnings,
        generated_at=datetime.now(UTC).isoformat(),
    )


def _build_evidence(scan: ProjectScanResult) -> list[RepoMapEvidence]:
    evidence: list[RepoMapEvidence] = []
    if scan.package.found:
        evidence.append(_evidence("package.json", "package.json", "Frontend package metadata, scripts, and dependencies.", "read_config"))
    if scan.java_build.found:
        build_path = "pom.xml" if scan.java_build.build_tool == "maven" else "build.gradle" if scan.java_build.build_tool == "gradle" else "<file_tree>"
        evidence.append(_evidence(build_path, build_path, "Java build metadata and dependencies.", "read_config"))
    for entrypoint in scan.entrypoints:
        evidence.append(_evidence(entrypoint.path, entrypoint.path, f"Detected {entrypoint.kind} entrypoint.", "find_entrypoints"))
    return _dedupe_evidence(evidence)


def _evidence(evidence_id: str, path: str, reason: str, tool: str) -> RepoMapEvidence:
    return RepoMapEvidence(
        id=_stable_id("ev", evidence_id),
        source="file",
        path=path,
        reason=reason,
        collected_by_tool=tool,
    )


def _build_repo_file(entry: FileTreeEntry, evidence_by_path: dict[str, str]) -> RepoMapFile:
    role = _file_role(entry.path)
    module_id = _module_id_for_role(role)
    evidence = [evidence_by_path[entry.path]] if entry.path in evidence_by_path else []
    return RepoMapFile(
        path=entry.path,
        role=role,
        language=_language_for_path(entry.path),
        framework=_framework_for_path(entry.path, role),
        importance_score=_importance_for_role(role),
        summary=_summary_for_role(role),
        related_modules=[module_id] if module_id else [],
        evidence=evidence,
    )


def _build_modules(files: list[RepoMapFile]) -> list[RepoMapModule]:
    grouped: dict[str, list[RepoMapFile]] = {}
    for file in files:
        for module_id in file.related_modules:
            grouped.setdefault(module_id, []).append(file)

    modules: list[RepoMapModule] = []
    for module_id, module_files in sorted(grouped.items()):
        name, module_type, responsibility = MODULE_DEFINITIONS[module_id]
        key_files = [file.path for file in sorted(module_files, key=lambda item: (-item.importance_score, item.path))[:8]]
        entry_files = [file.path for file in module_files if file.importance_score >= 0.85]
        evidence = sorted({evidence_id for file in module_files for evidence_id in file.evidence})
        modules.append(
            RepoMapModule(
                id=module_id,
                name=name,
                type=module_type,
                description=f"{name} module inferred from file paths and known framework conventions.",
                responsibility=responsibility,
                key_files=key_files,
                entry_files=entry_files,
                confidence=0.9 if evidence else 0.75,
                evidence=evidence,
            )
        )
    return modules


def _file_role(path: str) -> str:
    name = PurePosixPath(path).name
    lowered = path.lower()
    if name in {"package.json", "pom.xml", "build.gradle", "build.gradle.kts", "vite.config.ts", "vite.config.js"}:
        return "config"
    if "src/main/resources/application." in path:
        return "config"
    if path in {"src/main.ts", "src/main.js"} or name.endswith("Application.java"):
        return "app_entry"
    if "/router/" in lowered:
        return "router"
    if "/store/" in lowered or "/stores/" in lowered or "pinia" in lowered:
        return "store"
    if "/api/" in lowered or "request" in lowered or "axios" in lowered:
        return "api_client"
    if "/views/" in lowered or "/pages/" in lowered:
        return "view"
    if "/components/" in lowered or name.endswith(".vue"):
        return "component"
    if name.endswith("Controller.java"):
        return "controller"
    if name.endswith("Service.java") or name.endswith("ServiceImpl.java"):
        return "service"
    if name.endswith("Repository.java") or name.endswith("Mapper.java") or name.endswith("Dao.java"):
        return "repository"
    if "/test/" in lowered or path.startswith("src/test/"):
        return "test"
    return "source"


def _module_id_for_role(role: str) -> str | None:
    return {
        "config": "config",
        "app_entry": "app",
        "router": "router",
        "store": "store",
        "api_client": "api",
        "view": "views",
        "component": "components",
        "controller": "controller",
        "service": "service",
        "repository": "repository",
        "test": "test",
    }.get(role)


def _language_for_path(path: str) -> str | None:
    suffix = PurePosixPath(path).suffix
    return {
        ".vue": "Vue",
        ".ts": "TypeScript",
        ".js": "JavaScript",
        ".json": "JSON",
        ".java": "Java",
        ".xml": "XML",
        ".yml": "YAML",
        ".yaml": "YAML",
        ".properties": "Properties",
        ".gradle": "Gradle",
        ".kts": "Kotlin",
    }.get(suffix)


def _framework_for_path(path: str, role: str) -> str | None:
    if path.endswith(".vue") or role in {"router", "store", "api_client", "view", "component"}:
        return "Vue"
    if path.endswith(".java") or role in {"controller", "service", "repository"}:
        return "Spring Boot" if role == "controller" else "Java"
    if path == "pom.xml":
        return "Maven"
    if path.startswith("build.gradle"):
        return "Gradle"
    return None


def _importance_for_role(role: str) -> float:
    return {
        "app_entry": 1.0,
        "config": 0.9,
        "controller": 0.9,
        "router": 0.88,
        "service": 0.82,
        "store": 0.8,
        "api_client": 0.78,
        "repository": 0.72,
        "view": 0.7,
        "component": 0.55,
        "test": 0.35,
    }.get(role, 0.2)


def _summary_for_role(role: str) -> str:
    return {
        "app_entry": "Application entrypoint.",
        "config": "Configuration or build metadata.",
        "router": "Frontend route definition candidate.",
        "store": "State management candidate.",
        "api_client": "Frontend API/request wrapper candidate.",
        "view": "Screen-level frontend page candidate.",
        "component": "Reusable UI component candidate.",
        "controller": "Java HTTP endpoint candidate.",
        "service": "Java service/business logic candidate.",
        "repository": "Java persistence boundary candidate.",
        "test": "Test file.",
    }.get(role, "Source file.")


def _candidate_flow_paths(files: list[RepoMapFile], roles: set[str]) -> list[str]:
    return [file.path for file in files if file.role in roles]


def _candidate_auth_paths(files: list[RepoMapFile]) -> list[str]:
    keywords = ("auth", "login", "security", "token", "jwt", "permission", "user")
    return [file.path for file in files if any(keyword in file.path.lower() for keyword in keywords)]


def _java_packages(files: list[RepoMapFile]) -> set[str]:
    packages: set[str] = set()
    prefix = "src/main/java/"
    for file in files:
        if not file.path.startswith(prefix):
            continue
        relative = file.path.removeprefix(prefix)
        parts = relative.split("/")[:-1]
        if parts:
            packages.add(".".join(parts))
    return packages


def _dedupe_evidence(evidence: list[RepoMapEvidence]) -> list[RepoMapEvidence]:
    seen: set[tuple[str, str]] = set()
    unique: list[RepoMapEvidence] = []
    for item in evidence:
        key = (item.path, item.reason)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _stable_id(prefix: str, value: str) -> str:
    normalized = "".join(character if character.isalnum() else "_" for character in value.lower()).strip("_")
    return f"{prefix}_{normalized or 'unknown'}"
