"""Read-only local project scanner for the Phase 1 backend."""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from code_reader_agent.models import (
    Entrypoint,
    FileTreeEntry,
    JavaBuildInfo,
    PackageInfo,
    ProjectScanResult,
    StackTag,
)


IGNORED_DIRECTORIES = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    "coverage",
    "__pycache__",
    ".pytest_cache",
}

PACKAGE_MANAGER_LOCKS = (
    ("pnpm", "pnpm-lock.yaml"),
    ("yarn", "yarn.lock"),
    ("npm", "package-lock.json"),
    ("bun", "bun.lockb"),
    ("bun", "bun.lock"),
)

KNOWN_STACK_PACKAGES = {
    "vue": "Vue",
    "vite": "Vite",
    "typescript": "TypeScript",
    "pinia": "Pinia",
    "vue-router": "Vue Router",
    "axios": "Axios",
    "element-plus": "Element Plus",
}

KNOWN_JAVA_DEPENDENCIES = {
    "spring-boot-starter": "Spring Boot",
    "spring-boot-starter-web": "Spring Web",
    "spring-boot-starter-security": "Spring Security",
    "mybatis-spring-boot-starter": "MyBatis",
    "spring-boot-starter-data-jpa": "JPA",
    "junit-jupiter": "JUnit",
    "spring-boot-starter-test": "JUnit",
}

ENTRYPOINT_CANDIDATES = (
    ("src/main.ts", "app_entry"),
    ("src/main.js", "app_entry"),
    ("src/App.vue", "root_component"),
    ("src/router/index.ts", "router"),
    ("src/router/index.js", "router"),
    ("vite.config.ts", "vite_config"),
    ("vite.config.js", "vite_config"),
)

JAVA_CONFIG_CANDIDATES = (
    "src/main/resources/application.yml",
    "src/main/resources/application.yaml",
    "src/main/resources/application.properties",
)

JAVA_LAYER_SUFFIXES = (
    ("Application.java", "java_app_entry"),
    ("Controller.java", "java_controller"),
    ("Service.java", "java_service"),
    ("Repository.java", "java_repository"),
    ("Mapper.java", "java_mapper"),
)


class ProjectScanError(ValueError):
    """Raised when a project path cannot be scanned."""


def scan_project(project_path: str | Path) -> ProjectScanResult:
    """Scan a local project without modifying it or running project commands."""

    root = Path(project_path).expanduser()
    if not root.exists():
        raise ProjectScanError(f"Project path does not exist: {root}")
    if not root.is_dir():
        raise ProjectScanError(f"Project path is not a directory: {root}")

    warnings: list[str] = []
    file_tree = _scan_file_tree(root)
    package = _read_package_json(root, warnings)
    java_build = _read_java_build(root, file_tree, warnings)
    if not package.found and not java_build.found:
        warnings.append("package.json not found; package metadata and dependency-based stack detection are unavailable.")

    detected_stack = _detect_stack(package, java_build, file_tree)
    entrypoints = _find_entrypoints(root, file_tree)

    return ProjectScanResult(
        project_name=package.name or java_build.artifact_id or root.name,
        project_path=str(root.resolve()),
        file_tree=file_tree,
        package=package,
        java_build=java_build,
        detected_stack=detected_stack,
        entrypoints=entrypoints,
        warnings=warnings,
    )


def _scan_file_tree(root: Path) -> list[FileTreeEntry]:
    entries: list[FileTreeEntry] = []

    def walk(directory: Path, depth: int) -> None:
        children = sorted(directory.iterdir(), key=lambda item: (item.is_file(), item.name.lower()))
        for child in children:
            if child.is_dir() and child.name in IGNORED_DIRECTORIES:
                continue

            relative_path = child.relative_to(root).as_posix()
            kind = "directory" if child.is_dir() else "file"
            entries.append(
                FileTreeEntry(
                    path=relative_path,
                    name=child.name,
                    kind=kind,
                    depth=depth,
                )
            )
            if child.is_dir():
                walk(child, depth + 1)

    walk(root, depth=0)
    return entries


def _read_package_json(root: Path, warnings: list[str]) -> PackageInfo:
    package_path = root / "package.json"
    if not package_path.exists():
        return PackageInfo(found=False, package_manager=_detect_package_manager(root, None))

    try:
        raw_data = json.loads(package_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        warnings.append(f"package.json could not be parsed: {exc.msg}.")
        return PackageInfo(found=False, package_manager=_detect_package_manager(root, None))

    if not isinstance(raw_data, dict):
        warnings.append("package.json root value is not an object.")
        return PackageInfo(found=False, package_manager=_detect_package_manager(root, None))

    return PackageInfo(
        found=True,
        name=_optional_string(raw_data.get("name")),
        version=_optional_string(raw_data.get("version")),
        package_manager=_detect_package_manager(root, _optional_string(raw_data.get("packageManager"))),
        scripts=_string_dict(raw_data.get("scripts")),
        dependencies=_string_dict(raw_data.get("dependencies")),
        dev_dependencies=_string_dict(raw_data.get("devDependencies")),
    )


def _read_java_build(root: Path, file_tree: list[FileTreeEntry], warnings: list[str]) -> JavaBuildInfo:
    pom_path = root / "pom.xml"
    gradle_path = root / "build.gradle"
    gradle_kts_path = root / "build.gradle.kts"
    settings_path = root / "settings.gradle"
    settings_kts_path = root / "settings.gradle.kts"
    config_files = [
        relative_path
        for relative_path in JAVA_CONFIG_CANDIDATES
        if (root / relative_path).exists()
    ]

    if pom_path.exists():
        return _read_maven_build(pom_path, config_files, warnings)

    for build_path in (gradle_path, gradle_kts_path):
        if build_path.exists():
            settings_name = _read_gradle_project_name(settings_path, settings_kts_path)
            return _read_gradle_build(build_path, settings_name, config_files, warnings)

    if _looks_like_java_project(file_tree):
        return JavaBuildInfo(found=True, build_tool=None, config_files=config_files)

    return JavaBuildInfo(found=False, config_files=config_files)


def _read_maven_build(pom_path: Path, config_files: list[str], warnings: list[str]) -> JavaBuildInfo:
    try:
        root_element = ET.fromstring(pom_path.read_text(encoding="utf-8"))
    except ET.ParseError as exc:
        warnings.append(f"pom.xml could not be parsed: {exc}.")
        return JavaBuildInfo(found=False, build_tool="maven", config_files=config_files)

    return JavaBuildInfo(
        found=True,
        build_tool="maven",
        group_id=_maven_text(root_element, "groupId") or _maven_text(root_element, "parent/groupId"),
        artifact_id=_maven_text(root_element, "artifactId"),
        version=_maven_text(root_element, "version") or _maven_text(root_element, "parent/version"),
        dependencies=_maven_dependencies(root_element),
        config_files=config_files,
    )


def _detect_package_manager(root: Path, declared_package_manager: str | None) -> str | None:
    if declared_package_manager:
        return declared_package_manager.split("@", 1)[0]

    for manager, lock_file in PACKAGE_MANAGER_LOCKS:
        if (root / lock_file).exists():
            return manager

    return None


def _detect_stack(
    package: PackageInfo,
    java_build: JavaBuildInfo,
    file_tree: list[FileTreeEntry],
) -> list[StackTag]:
    detected: list[StackTag] = []
    all_dependencies = {
        **package.dependencies,
        **package.dev_dependencies,
    }

    for package_name, display_name in KNOWN_STACK_PACKAGES.items():
        if package_name in all_dependencies:
            detected.append(StackTag(name=display_name, source=f"package.json:{package_name}"))

    file_paths = {entry.path for entry in file_tree if entry.kind == "file"}

    if "TypeScript" not in {tag.name for tag in detected} and any(path.endswith(".ts") for path in file_paths):
        detected.append(StackTag(name="TypeScript", source="file_tree:*.ts", confidence=0.8))

    if "Vue" not in {tag.name for tag in detected} and any(path.endswith(".vue") for path in file_paths):
        detected.append(StackTag(name="Vue", source="file_tree:*.vue", confidence=0.8))

    if "Vite" not in {tag.name for tag in detected} and {"vite.config.ts", "vite.config.js"} & file_paths:
        detected.append(StackTag(name="Vite", source="file_tree:vite.config", confidence=0.8))

    if java_build.found:
        detected.append(StackTag(name="Java", source=_java_build_source(java_build), confidence=1.0))
    if java_build.build_tool == "maven":
        detected.append(StackTag(name="Maven", source="pom.xml", confidence=1.0))
    if java_build.build_tool == "gradle":
        detected.append(StackTag(name="Gradle", source="build.gradle", confidence=1.0))

    for dependency_name, version in java_build.dependencies.items():
        display_name = _known_java_stack_name(dependency_name)
        if display_name and display_name not in {tag.name for tag in detected}:
            source = f"{_java_build_source(java_build)}:{dependency_name}"
            detected.append(StackTag(name=display_name, source=source, confidence=1.0 if version is not None else 0.9))

    if "Java" not in {tag.name for tag in detected} and any(path.endswith(".java") for path in file_paths):
        detected.append(StackTag(name="Java", source="file_tree:*.java", confidence=0.8))
    if "Spring Boot" not in {tag.name for tag in detected} and any(path.endswith("Application.java") for path in file_paths):
        detected.append(StackTag(name="Spring Boot", source="file_tree:*Application.java", confidence=0.8))

    return detected


def _find_entrypoints(root: Path, file_tree: list[FileTreeEntry]) -> list[Entrypoint]:
    static_entrypoints = [
        Entrypoint(path=relative_path, kind=kind, exists=True)
        for relative_path, kind in ENTRYPOINT_CANDIDATES
        if (root / relative_path).exists()
    ]
    java_entrypoints = [
        Entrypoint(path=entry.path, kind=kind, exists=True)
        for entry in file_tree
        if entry.kind == "file"
        for suffix, kind in JAVA_LAYER_SUFFIXES
        if entry.path.startswith("src/main/java/") and entry.path.endswith(suffix)
    ]
    config_entrypoints = [
        Entrypoint(path=relative_path, kind="java_config", exists=True)
        for relative_path in JAVA_CONFIG_CANDIDATES
        if (root / relative_path).exists()
    ]
    return static_entrypoints + java_entrypoints + config_entrypoints


def _looks_like_java_project(file_tree: list[FileTreeEntry]) -> bool:
    return any(entry.kind == "file" and entry.path.startswith("src/main/java/") for entry in file_tree)


def _maven_text(root_element: ET.Element, path: str) -> str | None:
    parts = path.split("/")
    current: ET.Element | None = root_element
    for part in parts:
        if current is None:
            return None
        current = _find_xml_child(current, part)
    if current is None or current.text is None:
        return None
    value = current.text.strip()
    return value or None


def _maven_dependencies(root_element: ET.Element) -> dict[str, str | None]:
    dependencies: dict[str, str | None] = {}
    dependencies_element = _find_xml_child(root_element, "dependencies")
    if dependencies_element is None:
        return dependencies
    for dependency in _find_xml_children(dependencies_element, "dependency"):
        artifact_id = _maven_text(dependency, "artifactId")
        if artifact_id is None:
            continue
        dependencies[artifact_id] = _maven_text(dependency, "version")
    return dependencies


def _find_xml_child(element: ET.Element, local_name: str) -> ET.Element | None:
    for child in list(element):
        if _local_xml_name(child.tag) == local_name:
            return child
    return None


def _find_xml_children(element: ET.Element, local_name: str) -> list[ET.Element]:
    return [child for child in list(element) if _local_xml_name(child.tag) == local_name]


def _local_xml_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _read_gradle_project_name(settings_path: Path, settings_kts_path: Path) -> str | None:
    for path in (settings_path, settings_kts_path):
        if not path.exists():
            continue
        content = path.read_text(encoding="utf-8")
        match = re.search(r"rootProject\.name\s*=\s*[\"']([^\"']+)[\"']", content)
        if match:
            return match.group(1)
    return None


def _read_gradle_build(path: Path, settings_name: str | None, config_files: list[str], warnings: list[str]) -> JavaBuildInfo:
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        warnings.append(f"{path.name} could not be read: {exc}.")
        return JavaBuildInfo(found=False, build_tool="gradle", config_files=config_files)

    return JavaBuildInfo(
        found=True,
        build_tool="gradle",
        group_id=_gradle_assignment(content, "group"),
        artifact_id=settings_name,
        version=_gradle_assignment(content, "version"),
        dependencies=_gradle_dependencies(content),
        config_files=config_files,
    )


def _gradle_assignment(content: str, name: str) -> str | None:
    match = re.search(rf"^\s*{re.escape(name)}\s*=\s*[\"']([^\"']+)[\"']", content, flags=re.MULTILINE)
    return match.group(1) if match else None


def _gradle_dependencies(content: str) -> dict[str, str | None]:
    dependencies: dict[str, str | None] = {}
    for match in re.finditer(r"[\"']([A-Za-z0-9_.-]+):([A-Za-z0-9_.-]+):?([^\"']*)[\"']", content):
        artifact_id = match.group(2)
        version = match.group(3) or None
        dependencies[artifact_id] = version
    return dependencies


def _known_java_stack_name(dependency_name: str) -> str | None:
    for known_dependency, display_name in KNOWN_JAVA_DEPENDENCIES.items():
        if dependency_name == known_dependency:
            return display_name
    return None


def _java_build_source(java_build: JavaBuildInfo) -> str:
    if java_build.build_tool == "maven":
        return "pom.xml"
    if java_build.build_tool == "gradle":
        return "build.gradle"
    return "file_tree:src/main/java"


def _optional_string(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _string_dict(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(key): str(item) for key, item in value.items()}
