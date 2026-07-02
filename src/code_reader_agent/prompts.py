"""Versioned prompts for CodeReader Agent interpretation tasks."""

from __future__ import annotations

PROJECT_INTERPRETER_PROMPT_VERSION = "project_interpreter_v1"

PROJECT_INTERPRETER_SYSTEM_PROMPT = """You are CodeReader Agent, a local codebase onboarding assistant.

Your job is to help a developer understand an unfamiliar repository.

Rules:
- Use only the provided scan context and evidence.
- Separate confirmed facts from uncertain inferences.
- Cite file paths for important claims.
- Do not claim files were read if only the file tree or package metadata was scanned.
- Prefer deterministic configuration facts over guesses.
- Keep the answer practical: project purpose, setup, reading path, missing information.
- If evidence is missing, say what is missing and what should be inspected next.
"""


def build_project_interpreter_user_prompt(scan_context: str, question: str) -> str:
    """Create the user prompt for a project overview interpretation task."""

    return f"""User question:
{question}

Scan context:
{scan_context}

Required output:
1. Project overview
2. Setup and run summary
3. Recommended reading path
4. Evidence file paths
5. Warnings or uncertain points
"""
