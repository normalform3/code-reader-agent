"""Local JSON state for project sessions and registry management."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from hashlib import sha1
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from code_reader_agent.models import (
    AskConversation,
    AskConversationCreate,
    AskConversationUpdate,
    ModelSettings,
    ModelSettingsUpdate,
    ProjectMemory,
    ProjectSession,
    ProjectSessionCreate,
    ProjectSessionUpdate,
    RegistryDetailSection,
    RegistryItemCreate,
    RegistryItemUpdate,
    RegistrySkill,
    RegistryTool,
    SessionMemory,
)


DEFAULT_MODEL_SETTINGS = ModelSettings()


DEFAULT_TOOL_DEFINITIONS = [
    {
        "id": "import_github_repository",
        "name": "import_github_repository",
        "description": "导入公开 GitHub 仓库到本地只读缓存。",
        "notes": "只支持公开 GitHub URL；不运行仓库代码，不安装依赖。",
        "details": [
            {"title": "用途", "items": ["把公开 GitHub 仓库 clone 到本地只读缓存，作为后续扫描目标。"]},
            {"title": "输入", "items": ["github_url: https://github.com/owner/repo 或 .git 形式。"]},
            {"title": "输出", "items": ["project_name", "project_path", "github_url", "repository", "reused_cache", "warnings"]},
            {"title": "安全规则", "items": ["只支持公开 GitHub。", "不支持 token、private repo 或任意 Git host。", "不运行项目脚本，不安装依赖，不执行 Git hooks。"]},
            {"title": "实现位置", "items": ["code_reader_agent.github_importer.import_github_repository", "API: POST /api/projects/import-github"]},
            {"title": "LLM 白名单", "items": ["不直接暴露给 LLM tool loop；由前端/API 显式调用。"]},
        ],
    },
    {
        "id": "scan_project",
        "name": "scan_project",
        "description": "扫描项目文件树、配置、技术栈和入口候选。",
        "notes": "只读取元数据和允许的配置摘要，跳过依赖、构建产物和敏感文件。",
        "details": [
            {"title": "用途", "items": ["生成项目文件树、package/java build 摘要、技术栈标签和入口候选。"]},
            {"title": "输入", "items": ["project_path: 本地项目目录。"]},
            {"title": "输出", "items": ["ProjectScanResult", "file_tree", "package", "java_build", "detected_stack", "entrypoints", "warnings"]},
            {"title": "安全规则", "items": ["跳过 .git、node_modules、dist、build、虚拟环境和缓存目录。", "不读取业务源码全文。"]},
            {"title": "实现位置", "items": ["code_reader_agent.scanner.scan_project", "API: POST /api/projects/scan"]},
            {"title": "LLM 白名单", "items": ["允许在 /api/agent/run 的只读 tool loop 中调用。"]},
        ],
    },
    {
        "id": "build_repo_map",
        "name": "build_repo_map",
        "description": "基于扫描结果生成模块、文件角色、阅读建议和证据。",
        "notes": "Repo Map 是前端工作台和 Agent 上下文选择的结构化来源。",
        "details": [
            {"title": "用途", "items": ["把扫描结果整理成模块、文件角色、入口、阅读建议、evidence 和 warnings。"]},
            {"title": "输入", "items": ["project_path 或 ProjectScanResult。"]},
            {"title": "输出", "items": ["RepoMap", "project_summary", "modules", "files", "directory_insights", "reading_recommendations", "evidence"]},
            {"title": "安全规则", "items": ["只基于扫描结果和安全 read_file 摘录。", "不声称完整 AST 调用链。"]},
            {"title": "实现位置", "items": ["code_reader_agent.repo_map.builder.build_repo_map", "API: POST /api/projects/repo-map"]},
            {"title": "LLM 白名单", "items": ["允许在 /api/agent/run 的只读 tool loop 中调用。"]},
        ],
    },
    {
        "id": "read_file",
        "name": "read_file",
        "description": "读取项目内指定文件片段。",
        "notes": "禁止路径穿越，默认拒绝 .env、私钥、证书和 npm/pypi 凭据文件。",
        "details": [
            {"title": "用途", "items": ["读取项目内相对路径文件，可选行号范围，作为 evidence 片段。"]},
            {"title": "输入", "items": ["project_path", "relative_path", "line_range?: [start, end]"]},
            {"title": "输出", "items": ["ReadFileResult", "path", "content", "start_line", "end_line", "total_lines", "truncated", "warnings"]},
            {"title": "安全规则", "items": ["禁止 .. 越过项目根目录。", "拒绝 .env、.npmrc、.pypirc、私钥、证书等敏感文件。", "长文件默认截断。"]},
            {"title": "实现位置", "items": ["code_reader_agent.tools.read_only.read_file"]},
            {"title": "LLM 白名单", "items": ["允许在 /api/agent/run 的只读 tool loop 中调用。"]},
        ],
    },
    {
        "id": "search_code",
        "name": "search_code",
        "description": "在项目内搜索代码关键词。",
        "notes": "优先使用 ripgrep，失败时使用 Python fallback；跳过敏感文件。",
        "details": [
            {"title": "用途", "items": ["按字面量搜索代码关键词，返回匹配文件、行号和片段。"]},
            {"title": "输入", "items": ["project_path", "query", "globs?: string[]", "max_matches?: number"]},
            {"title": "输出", "items": ["SearchCodeResult", "query", "matches", "used_backend", "warnings"]},
            {"title": "安全规则", "items": ["跳过依赖目录、构建产物和敏感文件。", "无匹配返回空列表，不作为错误。"]},
            {"title": "实现位置", "items": ["code_reader_agent.tools.read_only.search_code"]},
            {"title": "LLM 白名单", "items": ["允许在 /api/agent/run 的只读 tool loop 中调用。"]},
        ],
    },
    {
        "id": "search_keyword",
        "name": "search_keyword",
        "description": "Ask 模式按关键词搜索项目文件。",
        "notes": "复用 search_code 的安全边界，可选 frontend/backend/config 粗粒度 scope。",
        "details": [
            {"title": "用途", "items": ["为模块解释、流程追踪和实现细节问题补充真实代码证据。"]},
            {"title": "输入", "items": ["project_path", "keyword", "scope?: frontend | backend | config"]},
            {"title": "输出", "items": ["SearchCodeResult"]},
            {"title": "安全规则", "items": ["跳过敏感文件、依赖目录和构建产物。"]},
            {"title": "实现位置", "items": ["code_reader_agent.tools.read_only.search_keyword"]},
            {"title": "LLM 白名单", "items": ["Ask 模式内部只读工具。"]},
        ],
    },
    {
        "id": "search_api_path",
        "name": "search_api_path",
        "description": "Ask 模式搜索接口路径定义和调用位置。",
        "notes": "复用 search_code 的安全边界，限制在常见前端、后端和配置文件类型。",
        "details": [
            {"title": "用途", "items": ["回答接口在哪里定义、在哪里调用、前后端如何关联。"]},
            {"title": "输入", "items": ["project_path", "api_path"]},
            {"title": "输出", "items": ["SearchCodeResult"]},
            {"title": "安全规则", "items": ["只读搜索，不读取敏感文件。"]},
            {"title": "实现位置", "items": ["code_reader_agent.tools.read_only.search_api_path"]},
            {"title": "LLM 白名单", "items": ["Ask 模式内部只读工具。"]},
        ],
    },
    {
        "id": "list_files",
        "name": "list_files",
        "description": "列出项目文件树，用于 Ask 模式补充目录证据。",
        "notes": "复用扫描器忽略规则，只返回相对路径和类型，不读取源码全文。",
        "details": [
            {"title": "用途", "items": ["为 Ask 模式补充目录结构和配置位置。"]},
            {"title": "输入", "items": ["project_path", "max_depth?: number"]},
            {"title": "输出", "items": ["FileTreeEntry 列表"]},
            {"title": "安全规则", "items": ["跳过 .git、node_modules、dist、build、虚拟环境和缓存目录。"]},
            {"title": "实现位置", "items": ["code_reader_agent.tools.read_only.list_files"]},
            {"title": "LLM 白名单", "items": ["Ask 模式内部只读工具；不作为写能力暴露。"]},
        ],
    },
    {
        "id": "search_symbol",
        "name": "search_symbol",
        "description": "搜索类名、函数名、组件名或方法名。",
        "notes": "基于 search_code 的安全封装，限制在常见源码文件类型。",
        "details": [
            {"title": "用途", "items": ["用户询问指定文件、类或组件但记忆中无法定位时补充搜索。"]},
            {"title": "输入", "items": ["project_path", "symbol"]},
            {"title": "输出", "items": ["SearchCodeResult"]},
            {"title": "安全规则", "items": ["跳过敏感文件和依赖目录。"]},
            {"title": "实现位置", "items": ["code_reader_agent.tools.read_only.search_symbol"]},
            {"title": "LLM 白名单", "items": ["Ask 模式内部只读工具。"]},
        ],
    },
    {
        "id": "parse_dependencies",
        "name": "parse_dependencies",
        "description": "解析 package.json、pom.xml、Gradle 和 Spring 配置摘要。",
        "notes": "复用 scanner 已支持的确定性依赖解析。",
        "details": [
            {"title": "用途", "items": ["回答技术栈、启动方式、配置类问题。"]},
            {"title": "输入", "items": ["project_path"]},
            {"title": "输出", "items": ["包管理器、scripts、前端依赖、Java 构建工具、Java 依赖、配置文件列表"]},
            {"title": "安全规则", "items": ["不读取 .env 和私有凭据文件。"]},
            {"title": "实现位置", "items": ["code_reader_agent.tools.read_only.parse_dependencies"]},
            {"title": "LLM 白名单", "items": ["Ask 模式内部只读工具。"]},
        ],
    },
    {
        "id": "parse_routes",
        "name": "parse_routes",
        "description": "轻量提取前端路由候选。",
        "notes": "正则解析 router/routes 文件，不做完整 AST。",
        "details": [
            {"title": "用途", "items": ["回答页面、路由和前端入口问题。"]},
            {"title": "输入", "items": ["project_path"]},
            {"title": "输出", "items": ["route path、file、line_number 候选"]},
            {"title": "安全规则", "items": ["只读项目内允许文件。"]},
            {"title": "实现位置", "items": ["code_reader_agent.tools.read_only.parse_routes"]},
            {"title": "LLM 白名单", "items": ["Ask 模式内部只读工具。"]},
        ],
    },
    {
        "id": "parse_api_calls",
        "name": "parse_api_calls",
        "description": "提取 axios、fetch、request 等前端接口调用候选。",
        "notes": "只输出候选，不声明完整调用链。",
        "details": [
            {"title": "用途", "items": ["回答接口在哪里被调用、前端如何请求后端。"]},
            {"title": "输入", "items": ["project_path"]},
            {"title": "输出", "items": ["path、method、client、file、line_number 候选"]},
            {"title": "安全规则", "items": ["只读源码文件，跳过敏感文件。"]},
            {"title": "实现位置", "items": ["code_reader_agent.tools.read_only.parse_api_calls"]},
            {"title": "LLM 白名单", "items": ["Ask 模式内部只读工具。"]},
        ],
    },
    {
        "id": "parse_controller",
        "name": "parse_controller",
        "description": "提取 Spring Controller 接口候选。",
        "notes": "基于注解正则，结果是候选级证据。",
        "details": [
            {"title": "用途", "items": ["回答后端接口路径、HTTP 方法和 Controller 方法。"]},
            {"title": "输入", "items": ["project_path"]},
            {"title": "输出", "items": ["path、method、backend_file、backend_method、line_number 候选"]},
            {"title": "安全规则", "items": ["只读取项目内 Controller 源码。"]},
            {"title": "实现位置", "items": ["code_reader_agent.tools.read_only.parse_controller"]},
            {"title": "LLM 白名单", "items": ["Ask 模式内部只读工具。"]},
        ],
    },
    {
        "id": "parse_mapper",
        "name": "parse_mapper",
        "description": "提取 Mapper、Repository、SQL/XML 映射候选。",
        "notes": "用于补充 Java 数据访问边界，不做 SQL 语义分析。",
        "details": [
            {"title": "用途", "items": ["回答数据访问、Mapper、Repository 相关问题。"]},
            {"title": "输入", "items": ["project_path"]},
            {"title": "输出", "items": ["path、kind 候选"]},
            {"title": "安全规则", "items": ["只读项目内源码或 XML 映射文件。"]},
            {"title": "实现位置", "items": ["code_reader_agent.tools.read_only.parse_mapper"]},
            {"title": "LLM 白名单", "items": ["Ask 模式内部只读工具。"]},
        ],
    },
    {
        "id": "detect_framework",
        "name": "detect_framework",
        "description": "识别 Vue/Vite/Java/Spring Boot 等技术栈标签。",
        "notes": "由扫描器和 Repo Map Builder 的确定性规则实现。",
        "details": [
            {"title": "用途", "items": ["根据配置文件、依赖和文件树识别技术栈标签。"]},
            {"title": "输入", "items": ["package.json 摘要", "Java build 摘要", "file_tree"]},
            {"title": "输出", "items": ["StackTag: name, source, confidence"]},
            {"title": "安全规则", "items": ["确定性规则优先。", "缺少依赖证据时使用低置信度文件树补充。"]},
            {"title": "实现位置", "items": ["code_reader_agent.scanner", "code_reader_agent.repo_map.builder"]},
            {"title": "LLM 白名单", "items": ["不是独立 LLM tool；包含在 scan_project / build_repo_map 结果中。"]},
        ],
    },
    {
        "id": "find_entrypoints",
        "name": "find_entrypoints",
        "description": "寻找前端入口、路由入口和 Spring Boot 入口候选。",
        "notes": "只返回存在的候选路径，不声称完整调用链。",
        "details": [
            {"title": "用途", "items": ["识别 Vite/Vue 入口、路由入口、Spring Boot Application 和配置入口。"]},
            {"title": "输入", "items": ["project_path", "file_tree"]},
            {"title": "输出", "items": ["Entrypoint: path, kind, exists"]},
            {"title": "安全规则", "items": ["只检查候选路径和文件名规则。", "不执行项目命令，不做动态运行分析。"]},
            {"title": "实现位置", "items": ["code_reader_agent.scanner"]},
            {"title": "LLM 白名单", "items": ["不是独立 LLM tool；包含在 scan_project 结果中。"]},
        ],
    },
    {
        "id": "generate_doc",
        "name": "generate_doc",
        "description": "生成结构化项目解读报告。",
        "notes": "基于 Repo Map、tool calls、evidence 和 warnings 输出。",
        "details": [
            {"title": "用途", "items": ["生成项目地图、模块说明、关键入口、阅读路线和调用链候选报告。"]},
            {"title": "输入", "items": ["RepoMap", "用户问题", "tool_calls", "evidence", "warnings"]},
            {"title": "输出", "items": ["ProjectReport", "project_map", "module_summaries", "key_entrypoints", "reading_route", "uncertainties"]},
            {"title": "安全规则", "items": ["回答必须绑定 evidence。", "调用链只作为候选，不声称完整追踪。"]},
            {"title": "实现位置", "items": ["code_reader_agent.runtime.analysis.build_project_report"]},
            {"title": "LLM 白名单", "items": ["不是独立 LLM tool；由 /api/agent/run 汇总生成。"]},
        ],
    },
]


DEFAULT_SKILL_DEFINITIONS = [
    {
        "id": "CodebaseOverviewSkill",
        "name": "CodebaseOverviewSkill",
        "description": "生成项目地图、模块说明、关键入口和阅读路线。",
        "notes": "默认启用，是陌生项目 onboarding 的基础 skill。",
        "details": [
            {"title": "适用场景", "items": ["用户要求项目解读报告、项目地图、模块说明、关键入口和阅读路线。"]},
            {"title": "触发条件", "items": ["默认启用。", "适用于陌生项目 onboarding 和整体结构理解。"]},
            {"title": "优先读取文件", "items": ["README.md", "package.json", "pom.xml", "build.gradle", "入口文件", "核心模块文件"]},
            {"title": "可用 tools", "items": ["scan_project", "build_repo_map", "read_file", "search_code"]},
            {"title": "输出格式", "items": ["project map", "module summaries", "key entrypoints", "reading route", "call chain candidates", "evidence", "uncertainties"]},
            {"title": "验证方式", "items": ["报告结论必须能追溯到 Repo Map 或 evidence。"]},
            {"title": "失败处理", "items": ["证据不足时输出 uncertainties，不把推断写成事实。"]},
        ],
    },
    {
        "id": "VueSkill",
        "name": "VueSkill",
        "description": "扫描 Vue 入口、路由、页面、组件、状态和 API 请求，并沉淀到 Code Knowledge Index。",
        "notes": "当 Repo Map 检测到 Vue、Vite、Vue Router、Pinia、main.ts/main.js 或 .vue 文件时启用。",
        "details": [
            {"title": "适用场景", "items": ["Vue/Vite 前端项目结构、页面、组件、路由、状态管理和 API 调用分析。"]},
            {"title": "触发条件", "items": ["检测到 Vue/Vite 依赖或技术栈标签。", "存在 src/main.ts、src/main.js 或 .vue 文件。"]},
            {"title": "优先读取文件", "items": ["vite.config.*", "src/main.*", "src/App.vue", "src/router/*", "src/views/*", "src/pages/*", "src/components/*", "src/stores/*"]},
            {"title": "可用 tools", "items": ["parse_routes", "parse_api_calls", "search_keyword", "read_file"]},
            {"title": "输出格式", "items": ["File Summary", "Route Index", "Frontend API Call Index", "Symbol Index", "Query Hints", "Answer Prompt"]},
            {"title": "验证方式", "items": ["入口、路由和 store 结论需要引用对应文件路径或 evidence 片段。"]},
            {"title": "失败处理", "items": ["找不到标准路由/store 时说明只基于文件结构推断。"]},
        ],
    },
    {
        "id": "SpringBootSkill",
        "name": "SpringBootSkill",
        "description": "扫描 Spring Boot 启动类、配置、Controller 接口和安全配置，并沉淀到 Code Knowledge Index。",
        "notes": "当 Repo Map 检测到 spring-boot 依赖、Spring 栈标签或 @SpringBootApplication 时启用。",
        "details": [
            {"title": "适用场景", "items": ["Spring Boot 启动入口、配置文件、Controller 接口、安全/认证配置分析。"]},
            {"title": "触发条件", "items": ["pom.xml 或 build.gradle 中包含 spring-boot。", "存在 @SpringBootApplication 或 Controller/Security 相关文件。"]},
            {"title": "优先读取文件", "items": ["*Application.java", "*Controller.java", "SecurityConfig", "SecurityFilterChain", "Jwt", "UserDetailsService", "application.yml/properties"]},
            {"title": "可用 tools", "items": ["parse_controller", "search_keyword", "read_file"]},
            {"title": "输出格式", "items": ["Project Memory.entryPoints", "Project Memory.configFiles", "API Index", "File Summary", "Symbol Index", "Query Hints", "Answer Prompt"]},
            {"title": "验证方式", "items": ["分层结论必须来自类名、路径、注解候选或配置 evidence。"]},
            {"title": "失败处理", "items": ["缺少构建配置或注解证据时标记为低置信度。"]},
        ],
    },
    {
        "id": "JavaWebSkill",
        "name": "JavaWebSkill",
        "description": "扫描 Java Web Controller、Service、Mapper/Repository、Entity/DTO/VO 分层结构。",
        "notes": "Skill 不是提示词；该项会参与文件扫描、索引构建、Ask 检索提示和工具规划。",
        "details": [
            {"title": "适用场景", "items": ["Java Web 分层项目阅读路径、模块职责和登录/用户链路候选分析。"]},
            {"title": "触发条件", "items": ["存在 src/main/java。", "存在 Controller、Service、Mapper、Repository、Entity、DTO、VO 或 Config 命名文件。", "存在 Spring MVC/Web 相关依赖。"]},
            {"title": "扫描目标", "items": ["**/*Controller.java", "**/*Service.java", "**/*ServiceImpl.java", "**/*Mapper.java", "**/*Repository.java", "**/*Entity.java", "**/*DTO.java", "**/*VO.java", "**/*Config.java"]},
            {"title": "可用 tools", "items": ["search_keyword", "read_file"]},
            {"title": "输出格式", "items": ["File Summary", "Symbol Index", "Module Summary", "Query Hints", "Answer Prompt"]},
            {"title": "失败处理", "items": ["只基于命名和路径输出候选，不声明精准跨文件调用链。"]},
        ],
    },
    {
        "id": "MyBatisSkill",
        "name": "MyBatisSkill",
        "description": "扫描 Mapper、XML、SQL 片段和实体/表映射候选。",
        "notes": "第一版是轻量规则实现，只输出候选映射，不做 SQL 语义分析。",
        "details": [
            {"title": "适用场景", "items": ["MyBatis Mapper、Mapper XML、SQL、实体类和可能的数据表分析。"]},
            {"title": "触发条件", "items": ["pom.xml 中包含 mybatis 或 mybatis-plus。", "存在 @Mapper、*Mapper.java、*Mapper.xml 或 mapper 目录。"]},
            {"title": "扫描目标", "items": ["**/*Mapper.java", "**/*Mapper.xml", "@Mapper", "@Select/@Insert/@Update/@Delete", "<select>/<insert>/<update>/<delete>"]},
            {"title": "可用 tools", "items": ["parse_mapper", "search_keyword", "read_file"]},
            {"title": "输出格式", "items": ["File Summary", "Symbol Index", "Data Model Index", "Mapper-to-Entity relation", "可能的 table name / SQL 信息"]},
            {"title": "失败处理", "items": ["无法确认实体或表名时只保留 Mapper 文件候选。"]},
        ],
    },
    {
        "id": "RestApiSkill",
        "name": "RestApiSkill",
        "description": "扫描后端 Controller 接口、前端 API 调用，并建立前后端接口映射候选。",
        "notes": "用于 API Index 和 Flow Index 候选构建；回答仍必须基于只读工具 evidence。",
        "details": [
            {"title": "适用场景", "items": ["接口定义、接口调用位置、前后端接口映射和登录接口链路候选分析。"]},
            {"title": "触发条件", "items": ["存在 Controller mapping 注解。", "前端存在 axios、fetch、request 或 src/api 调用。"]},
            {"title": "扫描目标", "items": ["@RequestMapping/@GetMapping/@PostMapping/@PutMapping/@DeleteMapping", "axios.get/post", "request(...)", "fetch(...)", "api/*.ts", "api/*.js"]},
            {"title": "可用 tools", "items": ["parse_controller", "parse_api_calls", "search_api_path", "search_keyword"]},
            {"title": "输出格式", "items": ["API Index", "Frontend API Call Index", "前后端接口映射关系", "Flow Index 候选"]},
            {"title": "失败处理", "items": ["前后端路径无法配对时分别保留后端接口和前端调用候选。"]},
        ],
    },
    {
        "id": "ApiFlowCandidateSkill",
        "name": "ApiFlowCandidateSkill",
        "description": "识别 API 请求链路候选证据。",
        "notes": "MVP 只输出候选证据，不声称完整链路追踪。",
        "details": [
            {"title": "适用场景", "items": ["识别前端 API 调用和后端接口候选。"]},
            {"title": "触发条件", "items": ["Repo Map 中存在 api_endpoints 或 api_flows。"]},
            {"title": "优先搜索关键词", "items": ["axios", "fetch", "request", "@GetMapping", "@PostMapping", "Controller"]},
            {"title": "可用 tools", "items": ["search_code", "read_file", "build_repo_map"]},
            {"title": "输出格式", "items": ["API 候选文件", "匹配行", "可能的数据流方向", "不确定点"]},
            {"title": "验证方式", "items": ["只展示搜索和文件证据，不输出完整调用链结论。"]},
            {"title": "失败处理", "items": ["无匹配时说明未找到 API 候选，而不是断言项目无 API。"]},
        ],
    },
    {
        "id": "AuthFlowCandidateSkill",
        "name": "AuthFlowCandidateSkill",
        "description": "识别登录认证流程候选证据。",
        "notes": "MVP 只输出候选证据和不确定提示。",
        "details": [
            {"title": "适用场景", "items": ["分析登录、认证、权限、token 和路由守卫候选。"]},
            {"title": "触发条件", "items": ["Repo Map 中存在 auth_flows，或用户问题涉及登录/认证/权限/token。"]},
            {"title": "优先搜索关键词", "items": ["login", "logout", "token", "auth", "permission", "beforeEach", "Authorization", "SecurityFilterChain", "Jwt"]},
            {"title": "可用 tools", "items": ["search_code", "read_file", "build_repo_map"]},
            {"title": "输出格式", "items": ["认证候选文件", "前端守卫/请求封装候选", "后端安全配置候选", "不确定点"]},
            {"title": "验证方式", "items": ["认证链路必须标记为候选，除非有足够 evidence 支撑。"]},
            {"title": "失败处理", "items": ["证据不足时明确说明无法确认完整登录流程。"]},
        ],
    },
    {
        "id": "project_overview_skill",
        "name": "project_overview_skill",
        "description": "回答项目用途、整体架构和主要模块问题。",
        "notes": "Legacy deterministic Skill Router 的默认项目总览 skill。",
        "details": [
            {"title": "适用场景", "items": ["用户询问项目是做什么的、整体架构、主要模块或项目结构。"]},
            {"title": "触发条件", "items": ["“这个项目是干什么的？”", "“介绍一下项目”", "“项目结构”"]},
            {"title": "优先读取文件", "items": ["package.json", "pom.xml", "build.gradle", "README.md", "src/main.*", "*Application.java", "*Controller.java"]},
            {"title": "可用 tools", "items": ["list_files", "read_file", "read_config", "detect_framework", "build_repo_map"]},
            {"title": "输出格式", "items": ["项目用途", "技术栈", "核心模块", "入口文件", "推荐阅读路径", "依据文件", "不确定点"]},
            {"title": "验证方式", "items": ["检查结论是否引用配置、入口文件或 evidence。"]},
            {"title": "失败处理", "items": ["缺少 README/package 信息时说明只能基于文件结构推断。"]},
        ],
    },
    {
        "id": "setup_analysis_skill",
        "name": "setup_analysis_skill",
        "description": "回答项目如何运行、构建和开发。",
        "notes": "命令建议必须来自 scripts、构建配置或明确标注的框架约定。",
        "details": [
            {"title": "适用场景", "items": ["用户询问怎么运行、启动命令、构建、测试或开发环境。"]},
            {"title": "触发条件", "items": ["“怎么运行？”", "“启动命令”", "“怎么构建？”", "run", "build", "setup"]},
            {"title": "优先读取文件", "items": ["package.json", "pom.xml", "build.gradle", "settings.gradle", "lockfile", "vite.config.*", "application.yml/properties"]},
            {"title": "可用 tools", "items": ["read_config", "read_file", "detect_framework"]},
            {"title": "输出格式", "items": ["包管理器", "Java 构建工具", "安装命令建议", "dev/build/preview 命令", "Maven/Gradle 候选命令", "环境变量提示", "依据文件"]},
            {"title": "验证方式", "items": ["启动命令必须来自 package scripts、构建配置或明确标注的框架约定。"]},
            {"title": "失败处理", "items": ["未找到 scripts 或构建配置时说明未找到标准启动方式。"]},
        ],
    },
    {
        "id": "frontend_analysis_skill",
        "name": "frontend_analysis_skill",
        "description": "分析前端结构、页面、组件和路由组织。",
        "notes": "优先读取 Vite、main、App、router、views/pages 和 components 候选文件。",
        "details": [
            {"title": "适用场景", "items": ["分析前端目录、页面、组件、路由和入口。"]},
            {"title": "触发条件", "items": ["“前端结构”", "“页面在哪里”", "“组件如何组织”", "frontend", "router"]},
            {"title": "优先搜索关键词", "items": ["createApp", "createRouter", "routes", "defineComponent", "setup"]},
            {"title": "优先读取文件", "items": ["vite.config.*", "src/main.*", "src/App.vue", "src/router/*", "src/views/*", "src/pages/*", "src/components/*"]},
            {"title": "可用 tools", "items": ["read_file", "search_code", "build_repo_map"]},
            {"title": "输出格式", "items": ["入口", "路由", "页面目录", "组件目录", "推荐阅读顺序", "依据文件"]},
            {"title": "失败处理", "items": ["不追踪完整页面到 API 数据流，只输出当前证据支持的候选。"]},
        ],
    },
]


class LocalStateError(ValueError):
    """Raised when the local JSON state cannot be loaded or saved."""


def list_project_sessions() -> list[ProjectSession]:
    """Return project sessions sorted by most recently updated first."""

    state = _read_state()
    sessions = [_parse_project_session(item) for item in state.get("project_sessions", [])]
    return sorted(sessions, key=lambda item: item.updated_at, reverse=True)


def upsert_project_session(payload: ProjectSessionCreate) -> ProjectSession:
    """Create a project session, or refresh an existing one for the same path."""

    state = _read_state()
    sessions = [_parse_project_session(item) for item in state.get("project_sessions", [])]
    now = _now()
    existing = next((item for item in sessions if item.project_path == payload.project_path), None)
    if existing:
        updated = existing.model_copy(
            update={
                "title": payload.title or existing.title,
                "project_name": payload.project_name,
                "github_url": payload.github_url or existing.github_url,
                "repository": payload.repository or existing.repository,
                "status": payload.status,
                "last_question": payload.last_question if payload.last_question is not None else existing.last_question,
                "last_error": payload.last_error,
                "updated_at": now,
            }
        )
        sessions = [updated if item.id == existing.id else item for item in sessions]
    else:
        updated = ProjectSession(
            id=_new_id("project"),
            title=payload.title or payload.repository or payload.project_name,
            project_name=payload.project_name,
            project_path=payload.project_path,
            github_url=payload.github_url,
            repository=payload.repository,
            status=payload.status,
            last_question=payload.last_question,
            last_error=payload.last_error,
            created_at=now,
            updated_at=now,
        )
        sessions.append(updated)
    state["project_sessions"] = [item.model_dump() for item in sessions]
    _write_state(state)
    return updated


def update_project_session(project_id: str, payload: ProjectSessionUpdate) -> ProjectSession:
    """Update an existing project session."""

    state = _read_state()
    sessions = [_parse_project_session(item) for item in state.get("project_sessions", [])]
    current = _find_project_session(sessions, project_id)
    updates = payload.model_dump(exclude_unset=True)
    updates = {key: value for key, value in updates.items() if value is not None}
    updated = current.model_copy(update={**updates, "updated_at": _now()})
    state["project_sessions"] = [updated.model_dump() if item.id == project_id else item.model_dump() for item in sessions]
    _write_state(state)
    return updated


def delete_project_session(project_id: str) -> None:
    """Remove a project from the sidebar history without touching cached repositories."""

    state = _read_state()
    sessions = [_parse_project_session(item) for item in state.get("project_sessions", [])]
    _find_project_session(sessions, project_id)
    state["project_sessions"] = [item.model_dump() for item in sessions if item.id != project_id]
    conversations = state.get("ask_conversations", {})
    if isinstance(conversations, dict):
        conversations.pop(project_id, None)
        state["ask_conversations"] = conversations
    _write_state(state)


def get_project_session(project_id: str) -> ProjectSession:
    """Return a persisted project session by id."""

    state = _read_state()
    sessions = [_parse_project_session(item) for item in state.get("project_sessions", [])]
    return _find_project_session(sessions, project_id)


def list_ask_conversations(project_id: str) -> list[AskConversation]:
    """Return Ask conversations for a project session, newest first."""

    state = _read_state()
    sessions = [_parse_project_session(item) for item in state.get("project_sessions", [])]
    _find_project_session(sessions, project_id)
    conversations = _parse_ask_conversations(state.get("ask_conversations", {}), project_id)
    return sorted(conversations, key=lambda item: item.updated_at, reverse=True)


def create_ask_conversation(project_id: str, payload: AskConversationCreate) -> AskConversation:
    """Create an empty Ask conversation for a project session."""

    state = _read_state()
    sessions = [_parse_project_session(item) for item in state.get("project_sessions", [])]
    project = _find_project_session(sessions, project_id)
    conversations = _ask_conversations_state(state)
    now = _now()
    conversation = AskConversation(
        id=_new_id("ask"),
        project_id=project.id,
        project_path=project.project_path,
        title=payload.title or "新对话",
        messages=[],
        session_memory=SessionMemory(project_id=project_id_for_path(project.project_path), updated_at=now),
        last_question=None,
        created_at=now,
        updated_at=now,
    )
    project_conversations = _parse_ask_conversations(conversations, project_id)
    project_conversations.append(conversation)
    conversations[project_id] = [item.model_dump() for item in project_conversations]
    state["ask_conversations"] = conversations
    _write_state(state)
    return conversation


def get_ask_conversation(project_id: str, conversation_id: str) -> AskConversation:
    """Return one Ask conversation by id."""

    conversations = list_ask_conversations(project_id)
    return _find_ask_conversation(conversations, conversation_id)


def get_ask_conversation_by_id(conversation_id: str) -> AskConversation:
    """Return one Ask conversation by globally unique id."""

    state = _read_state()
    conversations_state = _ask_conversations_state(state)
    for project_id in conversations_state:
        conversation = _find_ask_conversation_or_none(_parse_ask_conversations(conversations_state, str(project_id)), conversation_id)
        if conversation is not None:
            return conversation
    raise LocalStateError(f"Ask conversation not found: {conversation_id}")


def update_ask_conversation(project_id: str, conversation_id: str, payload: AskConversationUpdate) -> AskConversation:
    """Update an Ask conversation without persisting code context."""

    state = _read_state()
    sessions = [_parse_project_session(item) for item in state.get("project_sessions", [])]
    _find_project_session(sessions, project_id)
    conversations_state = _ask_conversations_state(state)
    conversations = _parse_ask_conversations(conversations_state, project_id)
    current = _find_ask_conversation(conversations, conversation_id)
    updates: dict[str, object] = {}
    if payload.title is not None:
        updates["title"] = payload.title
    if payload.messages is not None:
        updates["messages"] = payload.messages
    if payload.session_memory is not None:
        updates["session_memory"] = payload.session_memory
    if payload.last_question is not None:
        updates["last_question"] = payload.last_question
    updated = current.model_copy(update={**updates, "updated_at": _now()})
    conversations_state[project_id] = [updated.model_dump() if item.id == conversation_id else item.model_dump() for item in conversations]
    state["ask_conversations"] = conversations_state
    _write_state(state)
    return updated


def update_ask_conversation_by_id(conversation_id: str, payload: AskConversationUpdate) -> AskConversation:
    """Update an Ask conversation by globally unique id."""

    conversation = get_ask_conversation_by_id(conversation_id)
    return update_ask_conversation(conversation.project_id, conversation_id, payload)


def delete_ask_conversation(project_id: str, conversation_id: str) -> None:
    """Delete one Ask conversation without touching project memory."""

    state = _read_state()
    sessions = [_parse_project_session(item) for item in state.get("project_sessions", [])]
    _find_project_session(sessions, project_id)
    conversations_state = _ask_conversations_state(state)
    conversations = _parse_ask_conversations(conversations_state, project_id)
    _find_ask_conversation(conversations, conversation_id)
    conversations_state[project_id] = [item.model_dump() for item in conversations if item.id != conversation_id]
    state["ask_conversations"] = conversations_state
    _write_state(state)


def project_id_for_path(project_path: str) -> str:
    """Return the stable local memory id for a project path."""

    digest = sha1(str(Path(project_path).expanduser().resolve()).encode("utf-8")).hexdigest()[:16]
    return f"project-memory-{digest}"


def get_project_memory(project_path: str) -> ProjectMemory | None:
    """Load persisted project memory for a project path, if present."""

    state = _read_state()
    project_id = project_id_for_path(project_path)
    memories = state.get("project_memories", {})
    if not isinstance(memories, dict) or project_id not in memories:
        return None
    try:
        return ProjectMemory.model_validate(memories[project_id])
    except ValidationError as exc:
        raise LocalStateError("Local project memory state contains an invalid item.") from exc


def save_project_memory(memory: ProjectMemory) -> ProjectMemory:
    """Persist project memory in local JSON state."""

    state = _read_state()
    memories = state.get("project_memories", {})
    if not isinstance(memories, dict):
        memories = {}
    updated = memory.model_copy(update={"updated_at": _now()})
    memories[updated.project_id] = updated.model_dump()
    state["project_memories"] = memories
    _write_state(state)
    return updated


def get_session_memory(project_path: str) -> SessionMemory | None:
    """Load short Ask session memory for a project path, if present."""

    state = _read_state()
    project_id = project_id_for_path(project_path)
    memories = state.get("session_memories", {})
    if not isinstance(memories, dict) or project_id not in memories:
        return None
    try:
        return SessionMemory.model_validate(memories[project_id])
    except ValidationError as exc:
        raise LocalStateError("Local session memory state contains an invalid item.") from exc


def save_session_memory(memory: SessionMemory) -> SessionMemory:
    """Persist short Ask session memory in local JSON state."""

    state = _read_state()
    memories = state.get("session_memories", {})
    if not isinstance(memories, dict):
        memories = {}
    updated = memory.model_copy(update={"updated_at": _now()})
    memories[updated.project_id] = updated.model_dump()
    state["session_memories"] = memories
    _write_state(state)
    return updated


def get_model_settings() -> ModelSettings:
    """Load local Bailian model settings."""

    state = _read_state()
    raw_settings = state.get("model_settings", DEFAULT_MODEL_SETTINGS.model_dump())
    try:
        return ModelSettings.model_validate(raw_settings)
    except ValidationError as exc:
        raise LocalStateError("Local model settings state is invalid.") from exc


def update_model_settings(payload: ModelSettingsUpdate) -> ModelSettings:
    """Persist local Bailian model settings without storing secrets."""

    model = payload.model.strip()
    if not model:
        raise LocalStateError("Model name must not be empty.")
    current = get_model_settings()
    updated = current.model_copy(update={"provider": "bailian", "model": model, "updated_at": _now()})
    state = _read_state()
    state["model_settings"] = updated.model_dump()
    _write_state(state)
    return updated


def list_tools() -> list[RegistryTool]:
    """Return tool registry items with built-ins merged in."""

    state = _read_state()
    tools = _merge_builtin_items(state.get("tools", []), DEFAULT_TOOL_DEFINITIONS, RegistryTool)
    state["tools"] = [item.model_dump() for item in tools]
    _write_state(state)
    return tools


def create_tool(payload: RegistryItemCreate) -> RegistryTool:
    """Create a custom tool registry item."""

    tools = list_tools()
    item = _custom_registry_item(payload, RegistryTool)
    tools.append(item)
    _save_registry_items("tools", tools)
    return item


def update_tool(tool_id: str, payload: RegistryItemUpdate) -> RegistryTool:
    """Update a tool registry item."""

    tools = list_tools()
    updated = _update_registry_item(tools, tool_id, payload)
    _save_registry_items("tools", tools)
    return updated


def delete_tool(tool_id: str) -> RegistryTool | None:
    """Delete a custom tool, or disable a built-in tool."""

    tools = list_tools()
    item = _find_registry_item(tools, tool_id)
    if item.builtin:
        updated = item.model_copy(update={"enabled": False, "updated_at": _now()})
        tools = [updated if current.id == tool_id else current for current in tools]
        _save_registry_items("tools", tools)
        return updated
    _save_registry_items("tools", [current for current in tools if current.id != tool_id])
    return None


def list_skills() -> list[RegistrySkill]:
    """Return skill registry items with built-ins merged in."""

    state = _read_state()
    skills = _merge_builtin_items(state.get("skills", []), DEFAULT_SKILL_DEFINITIONS, RegistrySkill)
    state["skills"] = [item.model_dump() for item in skills]
    _write_state(state)
    return skills


def create_skill(payload: RegistryItemCreate) -> RegistrySkill:
    """Create a custom skill registry item."""

    skills = list_skills()
    item = _custom_registry_item(payload, RegistrySkill)
    skills.append(item)
    _save_registry_items("skills", skills)
    return item


def update_skill(skill_id: str, payload: RegistryItemUpdate) -> RegistrySkill:
    """Update a skill registry item."""

    skills = list_skills()
    updated = _update_registry_item(skills, skill_id, payload)
    _save_registry_items("skills", skills)
    return updated


def delete_skill(skill_id: str) -> RegistrySkill | None:
    """Delete a custom skill, or disable a built-in skill."""

    skills = list_skills()
    item = _find_registry_item(skills, skill_id)
    if item.builtin:
        updated = item.model_copy(update={"enabled": False, "updated_at": _now()})
        skills = [updated if current.id == skill_id else current for current in skills]
        _save_registry_items("skills", skills)
        return updated
    _save_registry_items("skills", [current for current in skills if current.id != skill_id])
    return None


def state_file_path() -> Path:
    """Return the local state file path."""

    state_dir = Path(os.environ.get("CODEREADER_STATE_DIR", ".codereader")).expanduser()
    return state_dir / "state.json"


def _read_state() -> dict[str, object]:
    path = state_file_path()
    if not path.exists():
        return _initial_state()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise LocalStateError(f"Local state file is invalid JSON: {path}") from exc
    except OSError as exc:
        raise LocalStateError(f"Could not read local state file: {path}") from exc
    if not isinstance(raw, dict):
        raise LocalStateError(f"Local state file must contain a JSON object: {path}")
    return {
        "project_sessions": raw.get("project_sessions", []),
        "tools": raw.get("tools", []),
        "skills": raw.get("skills", []),
        "project_memories": raw.get("project_memories", {}),
        "session_memories": raw.get("session_memories", {}),
        "ask_conversations": raw.get("ask_conversations", {}),
        "model_settings": raw.get("model_settings", DEFAULT_MODEL_SETTINGS.model_dump()),
    }


def _write_state(state: dict[str, object]) -> None:
    path = state_file_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp_path.replace(path)
    except OSError as exc:
        raise LocalStateError(f"Could not write local state file: {path}") from exc


def _initial_state() -> dict[str, object]:
    now = _now()
    return {
        "project_sessions": [],
        "tools": [_builtin_registry_item(item, RegistryTool, now).model_dump() for item in DEFAULT_TOOL_DEFINITIONS],
        "skills": [_builtin_registry_item(item, RegistrySkill, now).model_dump() for item in DEFAULT_SKILL_DEFINITIONS],
        "project_memories": {},
        "session_memories": {},
        "ask_conversations": {},
        "model_settings": DEFAULT_MODEL_SETTINGS.model_dump(),
    }


def _merge_builtin_items(
    stored_items: object,
    defaults: list[dict[str, object]],
    model: type[RegistryTool] | type[RegistrySkill],
) -> list[RegistryTool] | list[RegistrySkill]:
    now = _now()
    parsed: list[RegistryTool] | list[RegistrySkill] = []
    if isinstance(stored_items, list):
        for item in stored_items:
            try:
                parsed.append(model.model_validate(item))
            except ValidationError as exc:
                raise LocalStateError("Local registry state contains an invalid item.") from exc

    by_id = {item.id: item for item in parsed}
    merged: list[RegistryTool] | list[RegistrySkill] = []
    for definition in defaults:
        existing = by_id.pop(definition["id"], None)
        if existing:
            merged.append(
                existing.model_copy(
                    update={
                        "name": existing.name or definition["name"],
                        "description": existing.description or definition["description"],
                        "notes": existing.notes or definition["notes"],
                        "details": existing.details or _definition_details(definition),
                        "builtin": True,
                    }
                )
            )
        else:
            merged.append(_builtin_registry_item(definition, model, now))
    merged.extend(by_id.values())
    return sorted(merged, key=lambda item: (not item.builtin, item.name.lower()))


def _builtin_registry_item(
    definition: dict[str, object],
    model: type[RegistryTool] | type[RegistrySkill],
    now: str,
) -> RegistryTool | RegistrySkill:
    return model(
        id=str(definition["id"]),
        name=str(definition["name"]),
        description=str(definition["description"]),
        notes=str(definition["notes"]),
        details=_definition_details(definition),
        enabled=True,
        builtin=True,
        created_at=now,
        updated_at=now,
    )


def _custom_registry_item(
    payload: RegistryItemCreate,
    model: type[RegistryTool] | type[RegistrySkill],
) -> RegistryTool | RegistrySkill:
    now = _now()
    return model(
        id=_new_id("custom"),
        name=payload.name.strip(),
        description=payload.description.strip(),
        notes=payload.notes.strip(),
        details=payload.details,
        enabled=payload.enabled,
        builtin=False,
        created_at=now,
        updated_at=now,
    )


def _update_registry_item(
    items: list[RegistryTool] | list[RegistrySkill],
    item_id: str,
    payload: RegistryItemUpdate,
) -> RegistryTool | RegistrySkill:
    current = _find_registry_item(items, item_id)
    updates: dict[str, object] = {}
    if payload.name is not None:
        updates["name"] = payload.name.strip()
    if payload.description is not None:
        updates["description"] = payload.description.strip()
    if payload.notes is not None:
        updates["notes"] = payload.notes.strip()
    if payload.details is not None:
        updates["details"] = payload.details
    if payload.enabled is not None:
        updates["enabled"] = payload.enabled
    updated = current.model_copy(update={**updates, "updated_at": _now()})
    for index, item in enumerate(items):
        if item.id == item_id:
            items[index] = updated
            return updated
    raise LocalStateError(f"Registry item not found: {item_id}")


def _save_registry_items(key: str, items: list[RegistryTool] | list[RegistrySkill]) -> None:
    state = _read_state()
    state[key] = [item.model_dump() for item in items]
    _write_state(state)


def _definition_details(definition: dict[str, object]) -> list[RegistryDetailSection]:
    raw_details = definition.get("details", [])
    if not isinstance(raw_details, list):
        return []
    return [RegistryDetailSection.model_validate(item) for item in raw_details]


def _parse_project_session(item: object) -> ProjectSession:
    try:
        return ProjectSession.model_validate(item)
    except ValidationError as exc:
        raise LocalStateError("Local project session state contains an invalid item.") from exc


def _ask_conversations_state(state: dict[str, object]) -> dict[str, object]:
    conversations = state.get("ask_conversations", {})
    if not isinstance(conversations, dict):
        conversations = {}
    return conversations


def _parse_ask_conversations(raw_conversations: object, project_id: str) -> list[AskConversation]:
    if not isinstance(raw_conversations, dict):
        return []
    raw_items = raw_conversations.get(project_id, [])
    if not isinstance(raw_items, list):
        return []
    try:
        return [AskConversation.model_validate(item) for item in raw_items]
    except ValidationError as exc:
        raise LocalStateError("Local Ask conversation state contains an invalid item.") from exc


def _find_project_session(sessions: list[ProjectSession], project_id: str) -> ProjectSession:
    for item in sessions:
        if item.id == project_id:
            return item
    raise LocalStateError(f"Project session not found: {project_id}")


def _find_ask_conversation(conversations: list[AskConversation], conversation_id: str) -> AskConversation:
    for item in conversations:
        if item.id == conversation_id:
            return item
    raise LocalStateError(f"Ask conversation not found: {conversation_id}")


def _find_ask_conversation_or_none(conversations: list[AskConversation], conversation_id: str) -> AskConversation | None:
    for item in conversations:
        if item.id == conversation_id:
            return item
    return None


def _find_registry_item(
    items: list[RegistryTool] | list[RegistrySkill],
    item_id: str,
) -> RegistryTool | RegistrySkill:
    for item in items:
        if item.id == item_id:
            return item
    raise LocalStateError(f"Registry item not found: {item_id}")


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:12]}"


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
