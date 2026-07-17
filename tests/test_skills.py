from __future__ import annotations

from pathlib import Path

from code_reader_agent.memory.project_memory import build_project_memory
from code_reader_agent.repo_map.builder import build_repo_map
from code_reader_agent.runtime.ask_mode import run_ask_mode
from code_reader_agent.scanner import scan_project
from code_reader_agent.skills.registry import KNOWLEDGE_INDEX_VERSION, default_skill_registry
from tests.test_ask_mode import configure_llm, intent_response, llm_response, tool_call
from tests.test_scanner import write_minimal_java_project, write_minimal_vue_project


def write_spring_vue_login_project(root: Path) -> None:
    write_minimal_java_project(root)
    write_minimal_vue_project(root)

    java_root = root / "src" / "main" / "java" / "com" / "example" / "demo"
    (java_root / "AuthController.java").write_text(
        "package com.example.demo;\n\n"
        "import org.springframework.web.bind.annotation.PostMapping;\n"
        "import org.springframework.web.bind.annotation.RestController;\n\n"
        "@RestController\n"
        "public class AuthController {\n"
        "  @PostMapping(\"/api/login\")\n"
        "  public String login() { return \"token\"; }\n"
        "}\n",
        encoding="utf-8",
    )
    (java_root / "AuthServiceImpl.java").write_text(
        "package com.example.demo;\n\n"
        "public class AuthServiceImpl {\n"
        "  public String login(String username) { return username; }\n"
        "}\n",
        encoding="utf-8",
    )
    (java_root / "SecurityConfig.java").write_text(
        "package com.example.demo;\n\n"
        "import org.springframework.security.core.userdetails.UserDetailsService;\n"
        "import org.springframework.security.web.SecurityFilterChain;\n\n"
        "public class SecurityConfig {\n"
        "  SecurityFilterChain securityFilterChain() { return null; }\n"
        "  UserDetailsService userDetailsService() { return null; }\n"
        "}\n",
        encoding="utf-8",
    )
    (java_root / "UserMapper.java").write_text(
        "package com.example.demo;\n\n"
        "import org.apache.ibatis.annotations.Mapper;\n"
        "import org.apache.ibatis.annotations.Select;\n\n"
        "@Mapper\n"
        "public interface UserMapper {\n"
        "  @Select(\"select * from users where username = #{username}\")\n"
        "  UserEntity findByUsername(String username);\n"
        "}\n",
        encoding="utf-8",
    )
    (java_root / "UserEntity.java").write_text(
        "package com.example.demo;\n\n"
        "public class UserEntity {\n"
        "  private Long id;\n"
        "  private String username;\n"
        "}\n",
        encoding="utf-8",
    )
    mapper_xml = root / "src" / "main" / "resources" / "mapper"
    mapper_xml.mkdir(parents=True)
    (mapper_xml / "UserMapper.xml").write_text(
        "<mapper namespace=\"com.example.demo.UserMapper\">\n"
        "  <select id=\"findByUsername\" resultType=\"UserEntity\">\n"
        "    select * from users where username = #{username}\n"
        "  </select>\n"
        "</mapper>\n",
        encoding="utf-8",
    )
    (root / "src" / "views").mkdir(parents=True, exist_ok=True)
    (root / "src" / "views" / "Login.vue").write_text(
        "<script setup lang=\"ts\">\n"
        "import { login } from '../api/auth'\n"
        "</script>\n"
        "<template><form /></template>\n",
        encoding="utf-8",
    )
    (root / "src" / "api").mkdir(parents=True, exist_ok=True)
    (root / "src" / "api" / "auth.ts").write_text(
        "import axios from 'axios'\n"
        "export const login = () => axios.post('/api/login')\n",
        encoding="utf-8",
    )
    (root / "src" / "router" / "index.ts").write_text(
        "import { createRouter } from 'vue-router';\n"
        "export const routes = [{ path: '/login', component: () => import('../views/Login.vue') }]\n"
        "router.beforeEach(() => true)\n",
        encoding="utf-8",
    )


def test_default_skill_registry_detects_mvp_skills(tmp_path: Path) -> None:
    write_spring_vue_login_project(tmp_path)
    repo_map = build_repo_map(scan_project(tmp_path))

    active = default_skill_registry().detect_active_skills(repo_map)
    active_names = {item.skill.name for item in active}

    assert {"JavaWebSkill", "SpringBootSkill", "MyBatisSkill", "VueSkill", "RestApiSkill"} <= active_names
    assert all(item.confidence > 0 for item in active)
    assert all(item.reason for item in active)


def test_project_skill_router_only_scans_active_skills(tmp_path: Path) -> None:
    write_spring_vue_login_project(tmp_path)
    repo_map = build_repo_map(scan_project(tmp_path))
    registry = default_skill_registry()

    active = registry.route_project_skills(repo_map)
    scans = registry.run_scan(repo_map, active)

    assert [scan.skill_name for scan in scans] == [item.skill.name for item in active]
    assert {"JavaWebSkill", "SpringBootSkill", "VueSkill", "RestApiSkill"} <= {scan.skill_name for scan in scans}


def test_skill_scans_return_structured_indexes(tmp_path: Path) -> None:
    write_spring_vue_login_project(tmp_path)
    repo_map = build_repo_map(scan_project(tmp_path))
    registry = default_skill_registry()

    scans = registry.run_scan(repo_map, registry.detect_active_skills(repo_map))
    by_name = {result.skill_name: result for result in scans}

    assert any(file.path.endswith("AuthController.java") for file in by_name["SpringBootSkill"].files)
    assert any(api.path == "/api/login" and api.backend_method == "login" for api in by_name["SpringBootSkill"].apis)
    assert any(route.path == "/login" for route in by_name["VueSkill"].routes)
    assert any(call.path == "/api/login" and call.file == "src/api/auth.ts" for call in by_name["VueSkill"].frontend_api_calls)
    assert any(model.table == "users" for model in by_name["MyBatisSkill"].data_models)
    assert any(api.frontend_calls and api.backend_file for api in by_name["RestApiSkill"].apis)


def test_project_memory_merges_skill_indexes(tmp_path: Path) -> None:
    write_spring_vue_login_project(tmp_path)
    repo_map = build_repo_map(scan_project(tmp_path))

    memory = build_project_memory(repo_map)

    assert memory.knowledge_index_version == KNOWLEDGE_INDEX_VERSION
    assert {"SpringBootSkill", "VueSkill", "RestApiSkill"} <= {skill.name for skill in memory.active_skills}
    assert any(api.path == "/api/login" and "src/api/auth.ts" in api.frontend_calls for api in memory.api_index)
    assert any(route.path == "/login" for route in memory.route_index)
    assert any(call.path == "/api/login" for call in memory.frontend_api_call_index)
    assert any(model.table == "users" for model in memory.data_model_index)
    assert any(relation.mapper_file.endswith("UserMapper.java") for relation in memory.mapper_relations)


def test_ask_mode_uses_skill_hints_and_read_only_tool_plans(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.setenv("CODEREADER_STATE_DIR", str(tmp_path / "state"))
    write_spring_vue_login_project(tmp_path)
    configure_llm(
        monkeypatch,
        [
            intent_response("flow_trace", need_code_evidence=True),
            llm_response("读取认证控制器作为公开证据。", [tool_call("search_keyword", {"keyword": "AuthController"})]),
            llm_response("证据已足够。"),
            llm_response("登录功能由前端请求和认证控制器候选组成。"),
        ],
    )

    result = run_ask_mode(str(tmp_path), "登录功能是怎么实现的？")

    routed_names = {skill.name for skill in result.routed_skills}
    assert {"JavaWebSkill", "SpringBootSkill", "VueSkill", "RestApiSkill"} <= routed_names
    assert all(skill.confidence > 0 for skill in result.routed_skills)
    assert all(skill.reason for skill in result.routed_skills)
    hint_keywords = {hint.keyword for hint in result.query_hints}
    assert {"Login.vue", "auth.ts", "AuthController", "SecurityConfig", "UserDetailsService"} <= hint_keywords
    assert result.tool_plan and result.tool_plan.need_tools is False
    assert any(call.tool_name == "search_keyword" and call.input.get("keyword") == "AuthController" for call in result.tool_calls)
    assert result.tool_calls and all(call.reason and call.timestamp and call.duration_ms is not None for call in result.tool_calls)
    assert result.code_evidence


def test_question_skill_router_can_narrow_unrelated_skill_hints(tmp_path: Path, monkeypatch: object) -> None:
    monkeypatch.setenv("CODEREADER_STATE_DIR", str(tmp_path / "state"))
    write_minimal_vue_project(tmp_path)
    configure_llm(monkeypatch, [intent_response("config_lookup"), llm_response("不需要工具。"), llm_response("配置说明。")])

    result = run_ask_mode(str(tmp_path), "数据库配置在哪里？")

    assert result.intent == "config_lookup"
    assert result.routed_skills == []
    assert result.query_hints == []
    assert result.tool_plan and result.tool_plan.need_tools is False
