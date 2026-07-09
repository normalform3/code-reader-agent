"""Deterministic Repo Map builder for Phase 2."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import PurePosixPath

from code_reader_agent.models import (
    DirectoryInsight,
    FileTreeEntry,
    ProjectScanResult,
    ProjectSummary,
    ReadingRecommendation,
    RepoMap,
    RepoMapEvidence,
    RepoMapFile,
    RepoMapModule,
    StackExplanation,
)
from code_reader_agent.tools.read_only import ReadOnlyToolError, read_file


MODULE_DEFINITIONS = {
    "app": ("Application", "app", "Application bootstrap and top-level runtime wiring."),
    "router": ("Router", "router", "Frontend route definitions and navigation structure."),
    "store": ("State Store", "store", "Frontend state management and shared client state."),
    "api": ("API Client", "api", "Frontend API modules and request wrappers."),
    "views": ("Views", "views", "Routed pages and screen-level components."),
    "components": ("Components", "components", "Reusable UI components."),
    "hooks": ("Hooks", "hooks", "Reusable frontend composition logic."),
    "utils": ("Utilities", "utils", "Shared utility functions and helpers."),
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
    directory_insights = _build_directory_insights(scan.file_tree)
    reading_recommendations = _build_reading_recommendations(repo_files, directory_insights)

    return RepoMap(
        project_name=scan.project_name,
        project_path=scan.project_path,
        project_summary=_build_project_summary(scan, evidence),
        detected_stack=scan.detected_stack,
        stack_explanations=_build_stack_explanations(scan),
        directory_insights=directory_insights,
        reading_recommendations=reading_recommendations,
        package_manager=scan.package.package_manager,
        java_build_tool=scan.java_build.build_tool,
        run_scripts=scan.package.scripts,
        entrypoints=scan.entrypoints,
        modules=modules,
        files=repo_files,
        file_tree=scan.file_tree,
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
        for package_path in _file_tree_paths_named(scan.file_tree, {"package.json"}):
            evidence.append(
                _evidence(
                    scan.project_path,
                    package_path,
                    package_path,
                    "Frontend package metadata, scripts, and dependencies.",
                    "read_config",
                )
            )
    if scan.java_build.found:
        build_paths = _file_tree_paths_named(scan.file_tree, {"pom.xml", "build.gradle", "build.gradle.kts"})
        for build_path in build_paths or ["<file_tree>"]:
            evidence.append(_evidence(scan.project_path, build_path, build_path, "Java build metadata and dependencies.", "read_config"))
    for readme_path in ("README.md", "readme.md", "README.MD"):
        if any(entry.path == readme_path for entry in scan.file_tree):
            evidence.append(_evidence(scan.project_path, readme_path, readme_path, "Project README used for first-screen overview.", "read_readme"))
            break
    for entrypoint in scan.entrypoints:
        evidence.append(
            _evidence(
                scan.project_path,
                entrypoint.path,
                entrypoint.path,
                f"Detected {entrypoint.kind} entrypoint.",
                "find_entrypoints",
            )
        )
    return _dedupe_evidence(evidence)


def _evidence(project_path: str, evidence_id: str, path: str, reason: str, tool: str) -> RepoMapEvidence:
    collected_at = datetime.now(UTC).isoformat()
    if path.startswith("<"):
        return RepoMapEvidence(
            id=_stable_id("ev", evidence_id),
            source="file_tree",
            path=path,
            reason=reason,
            collected_by_tool=tool,
            collected_at=collected_at,
        )

    try:
        excerpt = read_file(project_path, path, line_range=(1, 40))
    except (ReadOnlyToolError, ValueError):
        return RepoMapEvidence(
            id=_stable_id("ev", evidence_id),
            source="file",
            path=path,
            reason=reason,
            collected_by_tool=tool,
            collected_at=collected_at,
        )

    return RepoMapEvidence(
        id=_stable_id("ev", evidence_id),
        source="file",
        path=path,
        reason=reason,
        collected_by_tool=tool,
        start_line=excerpt.start_line,
        end_line=excerpt.end_line,
        excerpt=excerpt.content,
        collected_at=collected_at,
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
                reading_priority=_module_reading_priority(module_id),
                confidence=0.9 if evidence else 0.75,
                evidence=evidence,
            )
        )
    return modules


def _build_project_summary(scan: ProjectScanResult, evidence: list[RepoMapEvidence]) -> ProjectSummary:
    readme = next((item for item in evidence if item.collected_by_tool == "read_readme" and item.excerpt), None)
    readme_text = _first_readme_sentence(readme.excerpt if readme else "")
    stack_names = [tag.name for tag in scan.detected_stack]
    stack_summary = "、".join(stack_names[:4]) if stack_names else "当前未识别出明确技术栈"
    evidence_paths = [item.path for item in evidence if item.path != "<file_tree>"][:4]

    has_frontend, has_backend = _scan_has_frontend_and_backend(scan)

    if readme_text:
        one_liner = f"{scan.project_name} 看起来是 {readme_text}"
        audience = "面向需要使用或维护该仓库的开发者；该判断来自 README 和项目配置。"
        problem = f"它主要解决 README 中描述的项目目标，并通过 {stack_summary} 等技术实现。"
        confidence = 0.78
    elif has_frontend and has_backend:
        one_liner = f"{scan.project_name} 看起来是一个基于 {stack_summary} 的前后端分离项目。"
        audience = "面向需要理解前端页面和后端接口协作关系的全栈开发者。"
        problem = "当前缺少 README 语义说明，只能根据前端 package、Java 构建配置、入口和分层文件保守判断项目用途。"
        confidence = 0.58
    elif scan.package.found:
        one_liner = f"{scan.project_name} 看起来是一个基于 {stack_summary} 的前端或 Node 项目。"
        audience = "面向项目使用者和维护该代码库的前端/全栈开发者。"
        problem = "当前缺少 README 语义说明，只能根据 package.json、依赖和入口文件保守判断项目用途。"
        confidence = 0.52
    elif scan.java_build.found:
        one_liner = f"{scan.project_name} 看起来是一个基于 {stack_summary} 的 Java 后端服务。"
        audience = "面向需要理解或维护该后端服务的开发者。"
        problem = "当前缺少 README 语义说明，只能根据 Java 构建配置、入口和分层文件保守判断项目用途。"
        confidence = 0.55
    else:
        one_liner = f"{scan.project_name} 是一个本地代码库；当前证据不足，无法可靠判断具体业务用途。"
        audience = "未知；需要继续读取 README、入口文件或核心源码确认。"
        problem = "当前只扫描到文件树，缺少可支撑业务判断的配置或说明文件。"
        confidence = 0.25

    return ProjectSummary(
        one_liner=one_liner,
        audience=audience,
        problem=problem,
        confidence=confidence,
        evidence=evidence_paths,
    )


def _first_readme_sentence(text: str) -> str:
    for raw_line in text.splitlines():
        line = raw_line.strip().strip("#").strip()
        if not line or line.startswith(("!", "[", "<")):
            continue
        if len(line) < 8:
            continue
        return line.rstrip("。.!") + "。"
    return ""


def _build_stack_explanations(scan: ProjectScanResult) -> list[StackExplanation]:
    return [
        StackExplanation(
            name=tag.name,
            category=_stack_category(tag.name),
            purpose=_stack_purpose(tag.name),
            evidence_source=tag.source,
            confidence=tag.confidence,
        )
        for tag in scan.detected_stack
    ]


def _stack_category(name: str) -> str:
    return {
        "Vue": "前端框架",
        "React": "前端框架",
        "Next.js": "前端框架",
        "Vite": "构建工具",
        "Webpack": "构建工具",
        "TypeScript": "语言",
        "Pinia": "状态管理",
        "Redux": "状态管理",
        "Zustand": "状态管理",
        "Vue Router": "路由",
        "FastAPI": "后端框架",
        "Spring Boot": "后端框架",
        "Spring Web": "后端接口",
        "Express": "后端框架",
        "Maven": "构建工具",
        "Gradle": "构建工具",
        "MySQL": "数据库",
        "PostgreSQL": "数据库",
        "SQLite": "数据库",
        "MongoDB": "数据库",
        "Pytest": "测试框架",
        "JUnit": "测试框架",
        "Vitest": "测试框架",
        "LangChain": "AI 框架",
        "LangGraph": "AI 工作流",
        "LlamaIndex": "AI 检索/索引",
        "Docker": "部署",
        "Vercel": "部署",
        "Netlify": "部署",
        "Kubernetes": "部署",
    }.get(name, "项目依赖")


def _stack_purpose(name: str) -> str:
    return {
        "Vue": "负责前端交互界面、页面组件和应用挂载。",
        "React": "负责前端交互界面和组件化页面。",
        "Next.js": "负责 React 应用路由、渲染和构建约定。",
        "Vite": "负责本地开发服务器、前端构建和插件配置。",
        "Webpack": "负责前端资源打包和构建配置。",
        "TypeScript": "为前端或 Node 代码提供类型约束。",
        "Pinia": "负责 Vue 应用的全局状态管理。",
        "Redux": "负责 React 应用的全局状态管理。",
        "Zustand": "负责轻量客户端状态管理。",
        "Vue Router": "负责 Vue 页面路由和导航关系。",
        "Axios": "负责浏览器端 HTTP 请求封装。",
        "FastAPI": "提供 Python 后端接口和本地 API 服务。",
        "Spring Boot": "提供 Java 后端应用启动和运行框架。",
        "Spring Web": "提供 Java HTTP Controller 和接口层能力。",
        "Spring Security": "提供 Java 认证、鉴权或安全过滤能力。",
        "Express": "提供 Node.js HTTP 接口服务。",
        "Maven": "负责 Java 依赖管理、构建和测试命令。",
        "Gradle": "负责 Java 依赖管理、构建和测试命令。",
        "MySQL": "作为关系型数据存储候选。",
        "PostgreSQL": "作为关系型数据存储候选。",
        "SQLite": "作为轻量本地数据库候选。",
        "MongoDB": "作为文档数据库候选。",
        "Pytest": "负责 Python 测试执行。",
        "JUnit": "负责 Java 单元测试和集成测试。",
        "Vitest": "负责前端单元测试。",
        "LangChain": "负责 LLM 应用链路、工具或模型调用抽象。",
        "LangGraph": "负责 Agent 工作流或状态图编排。",
        "LlamaIndex": "负责文档、代码片段或知识索引检索。",
        "Docker": "提供容器化运行或部署入口。",
        "Vercel": "提供前端或全栈应用部署配置。",
        "Netlify": "提供静态站点或前端应用部署配置。",
        "Kubernetes": "提供集群部署配置。",
    }.get(name, "根据依赖或文件结构识别出的项目组成部分，具体作用需要继续查看源码确认。")


def _build_directory_insights(file_tree: list[FileTreeEntry]) -> list[DirectoryInsight]:
    directories = {entry.path for entry in file_tree if entry.kind == "directory" and entry.depth <= 2}
    insights = [_directory_insight(path) for path in sorted(directories)]
    priority = {"core": 0, "supporting": 1, "skippable": 2}
    return sorted(insights, key=lambda item: (priority[item.importance], item.path))[:18]


def _directory_insight(path: str) -> DirectoryInsight:
    lowered = path.lower()
    if lowered in {"src", "app", "backend", "frontend"}:
        return DirectoryInsight(path=path, role="主要源码目录", importance="core", reason="通常包含应用入口、业务代码和主要运行逻辑。")
    if any(part in lowered for part in ("router", "routes")):
        return DirectoryInsight(path=path, role="路由目录", importance="core", reason="用于理解页面或接口如何对外暴露。")
    if any(part in lowered for part in ("views", "pages")):
        return DirectoryInsight(path=path, role="页面目录", importance="core", reason="用于理解主要用户界面和业务入口。")
    if "api" in lowered or "controller" in lowered:
        return DirectoryInsight(path=path, role="接口目录", importance="core", reason="用于理解前后端请求封装或后端 HTTP 入口。")
    if "service" in lowered:
        return DirectoryInsight(path=path, role="服务目录", importance="core", reason="通常承载业务逻辑边界。")
    if any(part in lowered for part in ("store", "stores")):
        return DirectoryInsight(path=path, role="状态管理目录", importance="core", reason="用于理解全局状态、登录态或跨页面数据。")
    if "component" in lowered:
        return DirectoryInsight(path=path, role="组件目录", importance="supporting", reason="包含复用 UI，建议在理解页面后按需阅读。")
    if any(part in lowered for part in ("hook", "composable")):
        return DirectoryInsight(path=path, role="复用逻辑目录", importance="supporting", reason="包含可复用逻辑，常被页面或组件调用。")
    if any(part in lowered for part in ("config", "resources")):
        return DirectoryInsight(path=path, role="配置目录", importance="supporting", reason="用于确认运行环境、插件或服务配置。")
    if any(part in lowered for part in ("test", "tests", "__tests__")):
        return DirectoryInsight(path=path, role="测试目录", importance="supporting", reason="用于理解已有验证方式，初读可在主流程后查看。")
    if any(part in lowered for part in ("asset", "assets", "style", "styles", "public")):
        return DirectoryInsight(path=path, role="静态资源或样式目录", importance="skippable", reason="通常不是理解核心业务流程的第一优先级。")
    if any(part in lowered for part in ("util", "utils", "lib")):
        return DirectoryInsight(path=path, role="工具目录", importance="supporting", reason="包含通用辅助函数，可在遇到调用时再读。")
    return DirectoryInsight(path=path, role="普通目录", importance="supporting", reason="当前只能根据目录名低置信度判断，建议按需查看。")


def _build_reading_recommendations(files: list[RepoMapFile], directories: list[DirectoryInsight]) -> list[ReadingRecommendation]:
    read_first = [
        ReadingRecommendation(
            path=file.path,
            action="read_first",
            reason=_reading_reason_for_file(file),
            priority=index,
        )
        for index, file in enumerate(
            sorted(
                [file for file in files if file.importance_score >= 0.7],
                key=lambda item: (-item.importance_score, item.path),
            )[:8],
            start=1,
        )
    ]
    skip_items = [
        ReadingRecommendation(
            path=item.path,
            action="skip_for_now",
            reason=item.reason,
            priority=len(read_first) + index,
        )
        for index, item in enumerate([item for item in directories if item.importance == "skippable"][:5], start=1)
    ]
    return [*read_first, *skip_items]


def _reading_reason_for_file(file: RepoMapFile) -> str:
    return {
        "app_entry": "应用入口，先确认项目如何启动和挂载。",
        "config": "配置或构建入口，先确认项目如何运行。",
        "router": "路由入口，适合快速理解页面或接口组织。",
        "controller": "后端 HTTP 入口，适合从外部请求开始读。",
        "service": "业务逻辑边界，适合在入口之后继续阅读。",
        "store": "全局状态入口，适合理解登录态或跨页面数据。",
        "api_client": "请求封装入口，适合理解前端如何访问后端。",
        "repository": "数据访问边界，适合在业务逻辑之后阅读。",
        "view": "页面级入口，适合理解具体用户流程。",
    }.get(file.role, file.summary)


def _module_reading_priority(module_id: str) -> int:
    return {
        "config": 1,
        "app": 2,
        "router": 3,
        "views": 4,
        "api": 5,
        "controller": 5,
        "store": 6,
        "service": 7,
        "repository": 8,
        "components": 9,
        "hooks": 10,
        "utils": 11,
        "test": 12,
    }.get(module_id, 99)


def _file_role(path: str) -> str:
    name = PurePosixPath(path).name
    lowered = path.lower()
    if name in {"package.json", "pom.xml", "build.gradle", "build.gradle.kts", "vite.config.ts", "vite.config.js"}:
        return "config"
    if name in {"dockerfile", "vercel.json", "netlify.toml"} or lowered.endswith((".yml", ".yaml")) and ("/.github/" in lowered or "docker" in lowered):
        return "config"
    if "/src/main/resources/application." in f"/{path}":
        return "config"
    if path in {"src/main.ts", "src/main.js"} or path.endswith(("/src/main.ts", "/src/main.js")) or name.endswith("Application.java"):
        return "app_entry"
    if "/router/" in lowered:
        return "router"
    if "/store/" in lowered or "/stores/" in lowered or "pinia" in lowered:
        return "store"
    if "/api/" in lowered or "request" in lowered or "axios" in lowered:
        return "api_client"
    if "/services/" in lowered or "/service/" in lowered:
        return "service"
    if "/hooks/" in lowered or "/composables/" in lowered:
        return "hook"
    if "/utils/" in lowered or "/lib/" in lowered:
        return "utility"
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
    if "/test/" in lowered or path.startswith("src/test/") or "/src/test/" in f"/{lowered}":
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
        "hook": "hooks",
        "utility": "utils",
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
        ".tsx": "TypeScript",
        ".jsx": "JavaScript",
        ".py": "Python",
    }.get(suffix)


def _framework_for_path(path: str, role: str) -> str | None:
    if path.endswith(".vue") or role in {"router", "store", "api_client", "view", "component"}:
        return "Vue"
    if path.endswith((".tsx", ".jsx")):
        return "React"
    if path.endswith(".py"):
        return "Python"
    if path.endswith(".java") or role in {"controller", "service", "repository"}:
        return "Spring Boot" if role == "controller" else "Java"
    if PurePosixPath(path).name == "pom.xml":
        return "Maven"
    if PurePosixPath(path).name in {"build.gradle", "build.gradle.kts"}:
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
        "hook": 0.62,
        "component": 0.55,
        "utility": 0.3,
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
        "hook": "Reusable frontend logic candidate.",
        "utility": "Shared utility helper candidate.",
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
    for file in files:
        marker = "/src/main/java/"
        normalized = f"/{file.path}"
        if marker not in normalized:
            continue
        relative = normalized.split(marker, 1)[1]
        parts = relative.split("/")[:-1]
        if parts:
            packages.add(".".join(parts))
    return packages


def _file_tree_paths_named(file_tree: list[FileTreeEntry], names: set[str]) -> list[str]:
    return sorted(entry.path for entry in file_tree if entry.kind == "file" and PurePosixPath(entry.path).name in names)


def _scan_has_frontend_and_backend(scan: ProjectScanResult) -> tuple[bool, bool]:
    stack_names = {tag.name for tag in scan.detected_stack}
    has_frontend = bool(stack_names & {"Vue", "Vite", "React", "Next.js"} or scan.package.found)
    has_backend = bool(stack_names & {"Spring Boot", "Spring Web", "Java", "FastAPI", "Express"} or scan.java_build.found)
    return has_frontend, has_backend


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
