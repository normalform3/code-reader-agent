"""FastAPI entrypoint for the local CodeReader Agent API."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from code_reader_agent.interpreter import interpret_project
from code_reader_agent.models import (
    AgentRunRequest,
    AgentRunResult,
    ProjectInterpretationRequest,
    ProjectInterpretationResult,
    ProjectScanResult,
    RepoMap,
)
from code_reader_agent.repo_map.builder import build_repo_map
from code_reader_agent.runtime.agent_loop import run_agent_loop
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


@app.post("/api/projects/repo-map", response_model=RepoMap)
def build_repo_map_api(request: ProjectScanRequest) -> RepoMap:
    """Scan a local project path and return a deterministic Repo Map."""

    try:
        return build_repo_map(scan_project(request.project_path))
    except ProjectScanError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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
        return run_agent_loop(request.project_path, request.question, request.max_steps)
    except ProjectScanError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
