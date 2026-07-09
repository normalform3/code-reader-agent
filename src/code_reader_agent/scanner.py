"""Read-only local project scanner for the Phase 1 backend."""

from __future__ import annotations

import json
import re
import tomllib
import xml.etree.ElementTree as ET
from pathlib import Path, PurePath
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
    "react": "React",
    "next": "Next.js",
    "vite": "Vite",
    "webpack": "Webpack",
    "typescript": "TypeScript",
    "pinia": "Pinia",
    "redux": "Redux",
    "@reduxjs/toolkit": "Redux",
    "zustand": "Zustand",
    "vue-router": "Vue Router",
    "axios": "Axios",
    "express": "Express",
    "mysql2": "MySQL",
    "mysql": "MySQL",
    "pg": "PostgreSQL",
    "sqlite3": "SQLite",
    "better-sqlite3": "SQLite",
    "mongodb": "MongoDB",
    "mongoose": "MongoDB",
    "vitest": "Vitest",
    "jest": "Jest",
    "langchain": "LangChain",
    "@langchain/core": "LangChain",
    "@langchain/langgraph": "LangGraph",
    "element-plus": "Element Plus",
}

KNOWN_PYTHON_DEPENDENCIES = {
    "fastapi": "FastAPI",
    "pytest": "Pytest",
    "langchain": "LangChain",
    "langgraph": "LangGraph",
    "llama-index": "LlamaIndex",
    "llama_index": "LlamaIndex",
    "chromadb": "Chroma",
    "pymysql": "MySQL",
    "mysqlclient": "MySQL",
    "psycopg": "PostgreSQL",
    "psycopg2": "PostgreSQL",
    "pymongo": "MongoDB",
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

CONFIG_DISCOVERY_MAX_DEPTH = 2


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
    package = _read_package_json(root, file_tree, warnings)
    java_build = _read_java_build(root, file_tree, warnings)
    if not package.found and not java_build.found:
        warnings.append("package.json not found; package metadata and dependency-based stack detection are unavailable.")

    detected_stack = _detect_stack(root, package, java_build, file_tree)
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


def _read_package_json(root: Path, file_tree: list[FileTreeEntry], warnings: list[str]) -> PackageInfo:
    package_paths = _config_paths(root, file_tree, ("package.json",))
    if not package_paths:
        return PackageInfo(found=False, package_manager=_detect_package_manager(root, None))

    packages: list[tuple[str, Path, dict[str, Any]]] = []
    for package_path in package_paths:
        relative_path = package_path.relative_to(root).as_posix()
        try:
            raw_data = json.loads(package_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            warnings.append(f"{relative_path} could not be parsed: {exc.msg}.")
            continue
        if not isinstance(raw_data, dict):
            warnings.append(f"{relative_path} root value is not an object.")
            continue
        packages.append((relative_path, package_path.parent, raw_data))

    if not packages:
        return PackageInfo(found=False, package_manager=_detect_package_manager(root, None))

    scripts: dict[str, str] = {}
    dependencies: dict[str, str] = {}
    dev_dependencies: dict[str, str] = {}
    package_manager: str | None = None
    first_package = packages[0][2]
    for relative_path, package_root, raw_data in packages:
        prefix = _config_parent_prefix(relative_path)
        for name, command in _string_dict(raw_data.get("scripts")).items():
            scripts[_prefixed_script_name(prefix, name)] = command
        dependencies.update(_string_dict(raw_data.get("dependencies")))
        dev_dependencies.update(_string_dict(raw_data.get("devDependencies")))
        package_manager = package_manager or _detect_package_manager(package_root, _optional_string(raw_data.get("packageManager")))

    return PackageInfo(
        found=True,
        name=_optional_string(first_package.get("name")),
        version=_optional_string(first_package.get("version")),
        package_manager=package_manager,
        scripts=scripts,
        dependencies=dependencies,
        dev_dependencies=dev_dependencies,
    )


def _read_java_build(root: Path, file_tree: list[FileTreeEntry], warnings: list[str]) -> JavaBuildInfo:
    config_files = _java_config_files(file_tree)
    maven_paths = _config_paths(root, file_tree, ("pom.xml",))
    gradle_paths = _config_paths(root, file_tree, ("build.gradle", "build.gradle.kts"))
    builds: list[tuple[str, JavaBuildInfo]] = []

    for pom_path in maven_paths:
        relative_path = pom_path.relative_to(root).as_posix()
        builds.append((relative_path, _read_maven_build(pom_path, _scoped_java_config_files(relative_path, config_files), warnings)))

    for build_path in gradle_paths:
        relative_path = build_path.relative_to(root).as_posix()
        build_root = build_path.parent
        settings_name = _read_gradle_project_name(build_root / "settings.gradle", build_root / "settings.gradle.kts")
        builds.append((relative_path, _read_gradle_build(build_path, settings_name, _scoped_java_config_files(relative_path, config_files), warnings)))

    valid_builds = [(path, build) for path, build in builds if build.found]
    if valid_builds:
        return _merge_java_builds(valid_builds, config_files)

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
    root: Path,
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

    if "Vite" not in {tag.name for tag in detected} and any(PurePath(path).name in {"vite.config.ts", "vite.config.js"} for path in file_paths):
        detected.append(StackTag(name="Vite", source="file_tree:vite.config", confidence=0.8))
    if "Next.js" not in {tag.name for tag in detected} and any(PurePath(path).name in {"next.config.ts", "next.config.js", "next.config.mjs"} for path in file_paths):
        detected.append(StackTag(name="Next.js", source="file_tree:next.config", confidence=0.8))
    if "React" not in {tag.name for tag in detected} and any(path.endswith((".tsx", ".jsx")) for path in file_paths):
        detected.append(StackTag(name="React", source="file_tree:*.tsx|*.jsx", confidence=0.65))

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

    for dependency_name, display_name in _python_dependency_names(root).items():
        if display_name not in {tag.name for tag in detected}:
            detected.append(StackTag(name=display_name, source=f"python_dependency:{dependency_name}", confidence=0.85))

    deployment_markers = {
        "Docker": ("Dockerfile", "docker-compose.yml", "docker-compose.yaml"),
        "Vercel": ("vercel.json",),
        "Netlify": ("netlify.toml",),
        "Kubernetes": ("k8s", "kubernetes"),
    }
    for display_name, markers in deployment_markers.items():
        if display_name in {tag.name for tag in detected}:
            continue
        if any(marker in file_paths or any(path.startswith(f"{marker}/") for path in file_paths) for marker in markers):
            detected.append(StackTag(name=display_name, source=f"file_tree:{display_name.lower()}", confidence=0.8))

    return detected


def _python_dependency_names(root: Path) -> dict[str, str]:
    detected: dict[str, str] = {}
    pyproject_path = root / "pyproject.toml"
    if pyproject_path.exists():
        try:
            pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
        except (tomllib.TOMLDecodeError, UnicodeDecodeError):
            pyproject = {}
        dependencies = pyproject.get("project", {}).get("dependencies", [])
        optional_dependencies = pyproject.get("project", {}).get("optional-dependencies", {})
        for raw_dependency in [*dependencies, *_flatten_dependency_groups(optional_dependencies)]:
            dependency_name = _normalize_python_dependency(raw_dependency)
            if dependency_name in KNOWN_PYTHON_DEPENDENCIES:
                detected[dependency_name] = KNOWN_PYTHON_DEPENDENCIES[dependency_name]

    requirements_path = root / "requirements.txt"
    if requirements_path.exists():
        try:
            lines = requirements_path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            lines = []
        for line in lines:
            dependency_name = _normalize_python_dependency(line)
            if dependency_name in KNOWN_PYTHON_DEPENDENCIES:
                detected[dependency_name] = KNOWN_PYTHON_DEPENDENCIES[dependency_name]
    return detected


def _flatten_dependency_groups(groups: object) -> list[str]:
    if not isinstance(groups, dict):
        return []
    dependencies: list[str] = []
    for group in groups.values():
        if isinstance(group, list):
            dependencies.extend(item for item in group if isinstance(item, str))
    return dependencies


def _normalize_python_dependency(raw_dependency: object) -> str:
    if not isinstance(raw_dependency, str):
        return ""
    dependency = raw_dependency.split(";", 1)[0].strip().lower()
    match = re.match(r"([a-z0-9_.-]+)", dependency)
    if not match:
        return ""
    return match.group(1).replace("_", "-")


def _find_entrypoints(root: Path, file_tree: list[FileTreeEntry]) -> list[Entrypoint]:
    file_paths = {entry.path for entry in file_tree if entry.kind == "file"}
    static_entrypoints = [
        Entrypoint(path=path, kind=kind, exists=True)
        for path in sorted(file_paths)
        for candidate_path, kind in ENTRYPOINT_CANDIDATES
        if path == candidate_path or path.endswith(f"/{candidate_path}")
    ]
    java_entrypoints = [
        Entrypoint(path=entry.path, kind=kind, exists=True)
        for entry in file_tree
        if entry.kind == "file"
        for suffix, kind in JAVA_LAYER_SUFFIXES
        if "/src/main/java/" in f"/{entry.path}" and entry.path.endswith(suffix)
    ]
    config_entrypoints = [
        Entrypoint(path=path, kind="java_config", exists=True)
        for path in _java_config_files(file_tree)
    ]
    return static_entrypoints + java_entrypoints + config_entrypoints


def _looks_like_java_project(file_tree: list[FileTreeEntry]) -> bool:
    return any(entry.kind == "file" and "/src/main/java/" in f"/{entry.path}" for entry in file_tree)


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


def _config_paths(root: Path, file_tree: list[FileTreeEntry], names: tuple[str, ...]) -> list[Path]:
    paths: list[Path] = []
    for entry in file_tree:
        if entry.kind != "file" or entry.name not in names:
            continue
        relative_parts = PurePath(entry.path).parts
        if len(relative_parts) - 1 > CONFIG_DISCOVERY_MAX_DEPTH:
            continue
        paths.append(root / entry.path)
    return sorted(paths, key=lambda item: (len(item.relative_to(root).parts), item.relative_to(root).as_posix()))


def _config_parent_prefix(relative_path: str) -> str:
    parent = PurePath(relative_path).parent.as_posix()
    return "" if parent == "." else parent.replace("/", ":")


def _prefixed_script_name(prefix: str, script_name: str) -> str:
    return f"{prefix}:{script_name}" if prefix else script_name


def _java_config_files(file_tree: list[FileTreeEntry]) -> list[str]:
    return sorted(
        entry.path
        for entry in file_tree
        if entry.kind == "file"
        and any(entry.path == candidate or entry.path.endswith(f"/{candidate}") for candidate in JAVA_CONFIG_CANDIDATES)
    )


def _scoped_java_config_files(build_relative_path: str, config_files: list[str]) -> list[str]:
    prefix = _config_parent_prefix(build_relative_path)
    if not prefix:
        return [path for path in config_files if path in JAVA_CONFIG_CANDIDATES]
    path_prefix = prefix.replace(":", "/")
    return [path for path in config_files if path.startswith(f"{path_prefix}/")]


def _merge_java_builds(builds: list[tuple[str, JavaBuildInfo]], config_files: list[str]) -> JavaBuildInfo:
    first_path, first_build = builds[0]
    dependencies: dict[str, str | None] = {}
    for _, build in builds:
        dependencies.update(build.dependencies)
    build_tools = {build.build_tool for _, build in builds if build.build_tool}
    build_tool = first_build.build_tool if len(build_tools) <= 1 else "mixed"
    return JavaBuildInfo(
        found=True,
        build_tool=build_tool,
        group_id=first_build.group_id,
        artifact_id=first_build.artifact_id or _config_parent_prefix(first_path) or None,
        version=first_build.version,
        dependencies=dependencies,
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
