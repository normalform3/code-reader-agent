"""FastAPI entrypoint for the local CodeReader Agent API."""

from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from code_reader_agent.github_importer import GitHubCloneError, GitHubImportError, import_github_repository
from code_reader_agent.interpreter import interpret_project
from code_reader_agent.local_state import (
    LocalStateError,
    create_ask_conversation,
    create_skill,
    create_tool,
    delete_ask_conversation,
    delete_project_session,
    delete_skill,
    delete_tool,
    get_ask_conversation_by_id,
    list_project_sessions,
    list_ask_conversations,
    list_skills,
    list_tools,
    get_model_settings,
    save_project_memory,
    update_ask_conversation,
    update_ask_conversation_by_id,
    update_model_settings,
    update_project_session,
    update_skill,
    update_tool,
    upsert_project_session,
)
from code_reader_agent.models import (
    AgentRunRequest,
    AgentRunResult,
    AskConversation,
    AskConversationCreate,
    AskConversationMessage,
    AskConversationUpdate,
    AskModeRequest,
    AskModeResult,
    GitHubImportRequest,
    GitHubImportResult,
    ModelConnectionTestResult,
    ModelSettingsStatus,
    ModelSettingsUpdate,
    ProjectInterpretationRequest,
    ProjectInterpretationResult,
    ProjectScanResult,
    ProjectSession,
    ProjectSessionCreate,
    ProjectSessionUpdate,
    RegistryItemCreate,
    RegistryItemUpdate,
    RegistrySkill,
    RegistryTool,
    RepoMap,
)
from code_reader_agent.runtime.ask_mode import run_ask_mode, run_ask_mode_events
from code_reader_agent.repo_map.builder import build_repo_map
from code_reader_agent.runtime.agent_loop import run_agent_loop
from code_reader_agent.runtime.llm_client import DEFAULT_API_KEY_ENV, DEFAULT_BASE_URL_ENV, LLMConfigurationError, LiteLLMClient
from code_reader_agent.scanner import ProjectScanError, scan_project


class ProjectScanRequest(BaseModel):
    project_path: str


app = FastAPI(title="CodeReader Agent API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/api/projects/scan", response_model=ProjectScanResult)
def scan_project_api(request: ProjectScanRequest) -> ProjectScanResult:
    """Scan a local project path and return deterministic metadata."""

    try:
        return scan_project(request.project_path)
    except ProjectScanError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/projects/import-github", response_model=GitHubImportResult)
def import_github_project_api(request: GitHubImportRequest) -> GitHubImportResult:
    """Import a public GitHub repository into the local read-only cache."""

    try:
        return import_github_repository(request.github_url)
    except GitHubImportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except GitHubCloneError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/projects/history", response_model=list[ProjectSession])
def list_project_history_api() -> list[ProjectSession]:
    """List locally saved project analysis sessions."""

    try:
        return list_project_sessions()
    except LocalStateError as exc:
        raise _state_http_error(exc) from exc


@app.post("/api/projects/history", response_model=ProjectSession)
def upsert_project_history_api(request: ProjectSessionCreate) -> ProjectSession:
    """Create or refresh a locally saved project analysis session."""

    try:
        return upsert_project_session(request)
    except LocalStateError as exc:
        raise _state_http_error(exc) from exc


@app.patch("/api/projects/history/{project_id}", response_model=ProjectSession)
def update_project_history_api(project_id: str, request: ProjectSessionUpdate) -> ProjectSession:
    """Patch a locally saved project analysis session."""

    try:
        return update_project_session(project_id, request)
    except LocalStateError as exc:
        raise _state_http_error(exc) from exc


@app.delete("/api/projects/history/{project_id}")
def delete_project_history_api(project_id: str) -> dict[str, bool]:
    """Remove a project from local history without deleting cached repositories."""

    try:
        delete_project_session(project_id)
        return {"deleted": True}
    except LocalStateError as exc:
        raise _state_http_error(exc) from exc


@app.get("/api/projects/{project_id}/ask-conversations", response_model=list[AskConversation])
def list_ask_conversations_api(project_id: str) -> list[AskConversation]:
    """List persisted Ask conversations for one project session."""

    try:
        return list_ask_conversations(project_id)
    except LocalStateError as exc:
        raise _state_http_error(exc) from exc


@app.post("/api/projects/{project_id}/ask-conversations", response_model=AskConversation)
def create_ask_conversation_api(project_id: str, request: AskConversationCreate) -> AskConversation:
    """Create a new Ask conversation under a project session."""

    try:
        return create_ask_conversation(project_id, request)
    except LocalStateError as exc:
        raise _state_http_error(exc) from exc


@app.patch("/api/projects/{project_id}/ask-conversations/{conversation_id}", response_model=AskConversation)
def update_ask_conversation_api(project_id: str, conversation_id: str, request: AskConversationUpdate) -> AskConversation:
    """Patch an Ask conversation without storing code context."""

    try:
        return update_ask_conversation(project_id, conversation_id, request)
    except LocalStateError as exc:
        raise _state_http_error(exc) from exc


@app.delete("/api/projects/{project_id}/ask-conversations/{conversation_id}")
def delete_ask_conversation_api(project_id: str, conversation_id: str) -> dict[str, bool]:
    """Remove one Ask conversation from local state."""

    try:
        delete_ask_conversation(project_id, conversation_id)
        return {"deleted": True}
    except LocalStateError as exc:
        raise _state_http_error(exc) from exc


@app.post("/api/projects/repo-map", response_model=RepoMap)
def build_repo_map_api(request: ProjectScanRequest) -> RepoMap:
    """Scan a local project path and return a deterministic Repo Map."""

    try:
        return build_repo_map(scan_project(request.project_path))
    except ProjectScanError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/registry/tools", response_model=list[RegistryTool])
def list_registry_tools_api() -> list[RegistryTool]:
    """List built-in and custom local tool registry items."""

    try:
        return list_tools()
    except LocalStateError as exc:
        raise _state_http_error(exc) from exc


@app.post("/api/registry/tools", response_model=RegistryTool)
def create_registry_tool_api(request: RegistryItemCreate) -> RegistryTool:
    """Create a custom local tool registry item."""

    try:
        return create_tool(request)
    except LocalStateError as exc:
        raise _state_http_error(exc) from exc


@app.patch("/api/registry/tools/{tool_id}", response_model=RegistryTool)
def update_registry_tool_api(tool_id: str, request: RegistryItemUpdate) -> RegistryTool:
    """Update a local tool registry item."""

    try:
        return update_tool(tool_id, request)
    except LocalStateError as exc:
        raise _state_http_error(exc) from exc


@app.delete("/api/registry/tools/{tool_id}", response_model=RegistryTool | None)
def delete_registry_tool_api(tool_id: str) -> RegistryTool | None:
    """Delete a custom tool, or disable a built-in tool."""

    try:
        return delete_tool(tool_id)
    except LocalStateError as exc:
        raise _state_http_error(exc) from exc


@app.get("/api/registry/skills", response_model=list[RegistrySkill])
def list_registry_skills_api() -> list[RegistrySkill]:
    """List built-in and custom local skill registry items."""

    try:
        return list_skills()
    except LocalStateError as exc:
        raise _state_http_error(exc) from exc


@app.post("/api/registry/skills", response_model=RegistrySkill)
def create_registry_skill_api(request: RegistryItemCreate) -> RegistrySkill:
    """Create a custom local skill registry item."""

    try:
        return create_skill(request)
    except LocalStateError as exc:
        raise _state_http_error(exc) from exc


@app.patch("/api/registry/skills/{skill_id}", response_model=RegistrySkill)
def update_registry_skill_api(skill_id: str, request: RegistryItemUpdate) -> RegistrySkill:
    """Update a local skill registry item."""

    try:
        return update_skill(skill_id, request)
    except LocalStateError as exc:
        raise _state_http_error(exc) from exc


@app.delete("/api/registry/skills/{skill_id}", response_model=RegistrySkill | None)
def delete_registry_skill_api(skill_id: str) -> RegistrySkill | None:
    """Delete a custom skill, or disable a built-in skill."""

    try:
        return delete_skill(skill_id)
    except LocalStateError as exc:
        raise _state_http_error(exc) from exc


@app.get("/api/model-settings", response_model=ModelSettingsStatus)
def get_model_settings_api() -> ModelSettingsStatus:
    """Return Bailian model settings and local runtime status."""

    try:
        return _model_settings_status()
    except LocalStateError as exc:
        raise _state_http_error(exc) from exc


@app.post("/api/model-settings", response_model=ModelSettingsStatus)
def update_model_settings_api(request: ModelSettingsUpdate) -> ModelSettingsStatus:
    """Update Bailian model name used by Agent and Ask mode."""

    try:
        update_model_settings(request)
        return _model_settings_status()
    except LocalStateError as exc:
        raise _state_http_error(exc) from exc


@app.post("/api/model-settings/test", response_model=ModelConnectionTestResult)
def test_model_settings_api() -> ModelConnectionTestResult:
    """Run a minimal Bailian connectivity test without exposing secrets."""

    try:
        settings = get_model_settings()
    except LocalStateError as exc:
        raise _state_http_error(exc) from exc

    client = LiteLLMClient(model=settings.model)
    missing = client.missing_environment_variables()
    if missing:
        return ModelConnectionTestResult(
            ok=False,
            model=client.config.model,
            message=f"Missing required environment variables: {', '.join(missing)}.",
            missing_environment=missing,
        )

    try:
        response = client.complete(
            [{"role": "user", "content": "只回复 OK，用于连通性测试。"}],
            tools=[],
        )
    except LLMConfigurationError as exc:
        return ModelConnectionTestResult(ok=False, model=client.config.model, message=str(exc))
    except Exception as exc:
        return ModelConnectionTestResult(ok=False, model=client.config.model, message=f"Model connection failed: {exc}")

    return ModelConnectionTestResult(
        ok=True,
        model=client.config.model,
        message="Bailian model connection succeeded.",
        response_preview=_extract_text_preview(response),
    )


@app.post("/api/agent/project-interpretation", response_model=ProjectInterpretationResult)
def interpret_project_api(request: ProjectInterpretationRequest) -> ProjectInterpretationResult:
    """Generate a Phase 4 single-agent project interpretation."""

    try:
        return interpret_project(request.project_path, request.question)
    except ProjectScanError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/agent/run", response_model=AgentRunResult)
def run_agent_api(request: AgentRunRequest) -> AgentRunResult:
    """Run the minimal read-only LLM agent loop with deterministic fallback."""

    try:
        return _run_agent_request(request)
    except ProjectScanError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LocalStateError as exc:
        raise _state_http_error(exc) from exc


@app.post("/api/agent/run/stream")
def run_agent_stream_api(request: AgentRunRequest) -> StreamingResponse:
    """Stream project-manual analysis progress events and final result as SSE."""

    def event_stream():
        try:
            yield _sse_event(
                "step",
                {
                    "type": "step",
                    "node": "Agent Runtime",
                    "event": {"title": "Create analysis task", "summary": "已创建只读项目说明书分析任务。", "status": "success"},
                },
            )
            scan = scan_project(request.project_path)
            yield _sse_event(
                "step",
                {
                    "type": "step",
                    "node": "Scanner",
                    "event": {
                        "title": "scan_project",
                        "summary": f"扫描到 {len(scan.file_tree)} 个文件树条目和 {len(scan.entrypoints)} 个入口候选。",
                        "status": "success",
                    },
                },
            )
            repo_map = build_repo_map(scan)
            yield _sse_event(
                "step",
                {
                    "type": "step",
                    "node": "Repo Map Builder",
                    "event": {
                        "title": "build_repo_map",
                        "summary": f"生成 {len(repo_map.modules)} 个模块、{len(repo_map.evidence)} 条 evidence。",
                        "status": "success",
                    },
                },
            )
            yield _sse_event(
                "step",
                {
                    "type": "step",
                    "node": "Project Manual",
                    "event": {"title": "generate_project_manual", "summary": "正在生成项目总览、关键目录和核心模块卡片。", "status": "success"},
                },
            )
            result = _run_agent_request(request)
            for event in result.trace_events:
                yield _sse_event("trace", {"type": "trace", "node": event.stage, "event": event.model_dump()})
            yield _sse_event("final", {"type": "final", "event": result.model_dump()})
        except (ProjectScanError, LocalStateError) as exc:
            yield _sse_event("error", {"type": "error", "error": str(exc)})
        except Exception as exc:
            yield _sse_event("error", {"type": "error", "error": f"Agent run stream failed: {exc}"})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/agent/ask", response_model=AskModeResult)
def ask_agent_api(request: AskModeRequest) -> AskModeResult:
    """Run report-side Ask mode against project memory and read-only tools."""

    try:
        conversation = get_ask_conversation_by_id(request.conversation_id) if request.conversation_id else None
        if conversation and conversation.project_path != request.project_path:
            raise LocalStateError("Ask conversation does not belong to the requested project path.")
        session_memory = conversation.session_memory if conversation else request.session_memory
        result = run_ask_mode(
            request.project_path,
            request.question,
            session_memory=session_memory,
            persist_session_memory=conversation is None,
        )
        if conversation:
            _persist_ask_conversation_turn(conversation, request.question, result)
        return result
    except ProjectScanError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LocalStateError as exc:
        raise _state_http_error(exc) from exc


@app.post("/api/agent/ask/stream")
def ask_agent_stream_api(request: AskModeRequest) -> StreamingResponse:
    """Stream report-side Ask progress events and final result as SSE."""

    def event_stream():
        try:
            conversation = get_ask_conversation_by_id(request.conversation_id) if request.conversation_id else None
            if conversation and conversation.project_path != request.project_path:
                raise LocalStateError("Ask conversation does not belong to the requested project path.")
            session_memory = conversation.session_memory if conversation else request.session_memory
            for event in run_ask_mode_events(
                request.project_path,
                request.question,
                session_memory=session_memory,
                persist_session_memory=conversation is None,
            ):
                if event["type"] == "final" and conversation:
                    event_payload = event.get("event", {})
                    result = AskModeResult.model_validate(event_payload)
                    conversation = _persist_ask_conversation_turn(conversation, request.question, result)
                    event["conversation"] = conversation.model_dump()
                yield _sse_event(event["type"], event)
        except (ProjectScanError, LocalStateError) as exc:
            yield _sse_event("error", {"type": "error", "error": str(exc)})
        except Exception as exc:
            yield _sse_event("error", {"type": "error", "error": f"Ask stream failed: {exc}"})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _persist_ask_conversation_turn(conversation: AskConversation, question: str, result: AskModeResult) -> AskConversation:
    now = _now()
    title = conversation.title
    if title == "新对话" and not conversation.messages:
        title = _conversation_title(question)
    messages = [
        *conversation.messages,
        AskConversationMessage(id=_new_message_id("user"), role="user", body=question, created_at=now),
        AskConversationMessage(
            id=_new_message_id("assistant"),
            role="assistant",
            body=result.answer,
            meta=f"Ask · {_intent_label(result.intent)} · {result.llm_model or '规则'}",
            created_at=now,
        ),
    ]
    return update_ask_conversation_by_id(
        conversation.id,
        AskConversationUpdate(
            title=title,
            messages=messages[-40:],
            session_memory=result.session_memory,
            last_question=question,
        ),
    )


def _conversation_title(question: str) -> str:
    value = " ".join(question.strip().split())
    return value[:28] or "新对话"


def _new_message_id(role: str) -> str:
    return f"{role}-{uuid4().hex[:12]}"


def _intent_label(intent: str) -> str:
    return {
        "project_overview": "项目总览",
        "module_explanation": "模块解释",
        "file_explanation": "文件解释",
        "flow_trace": "流程追踪",
        "api_lookup": "接口定位",
        "config_lookup": "配置定位",
        "tech_stack": "技术栈",
        "symbol_lookup": "符号定位",
        "general": "通用问题",
    }.get(intent, intent)


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _state_http_error(exc: LocalStateError) -> HTTPException:
    message = str(exc)
    if "not found" in message:
        return HTTPException(status_code=404, detail=message)
    return HTTPException(status_code=500, detail=message)


def _run_agent_request(request: AgentRunRequest) -> AgentRunResult:
    settings = get_model_settings()
    result = run_agent_loop(
        request.project_path,
        request.question,
        request.max_steps,
        max_context_chars=request.max_context_chars,
        max_tool_calls=request.max_tool_calls,
        max_read_files=request.max_read_files,
        llm_client=LiteLLMClient(model=settings.model),
        project_manual_context=request.project_manual_context,
    )
    if result.project_memory:
        save_project_memory(result.project_memory)
    return result


def _sse_event(event: str, payload: dict[str, object]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _model_settings_status() -> ModelSettingsStatus:
    settings = get_model_settings()
    client = LiteLLMClient(model=settings.model)
    missing = set(client.missing_environment_variables())
    return ModelSettingsStatus(
        provider="bailian",
        model=client.config.model,
        api_key_env=DEFAULT_API_KEY_ENV,
        base_url_env=DEFAULT_BASE_URL_ENV,
        api_key_configured=DEFAULT_API_KEY_ENV not in missing,
        base_url_configured=DEFAULT_BASE_URL_ENV not in missing,
        litellm_installed=importlib.util.find_spec("litellm") is not None,
        langgraph_installed=importlib.util.find_spec("langgraph") is not None,
        updated_at=settings.updated_at,
    )


def _extract_text_preview(response: object) -> str:
    content = ""
    if isinstance(response, dict):
        choices = response.get("choices")
        if isinstance(choices, list) and choices:
            message = choices[0].get("message") if isinstance(choices[0], dict) else None
            if isinstance(message, dict) and isinstance(message.get("content"), str):
                content = message["content"]
    else:
        choices = getattr(response, "choices", None)
        if choices:
            message = getattr(choices[0], "message", None)
            value = getattr(message, "content", None)
            content = value if isinstance(value, str) else ""
    return content.strip()[:240]
