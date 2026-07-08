"""Technology-stack skills for codebase understanding tasks."""

from code_reader_agent.skills.base import ActiveSkill, DetectResult, Skill
from code_reader_agent.skills.registry import KNOWLEDGE_INDEX_VERSION, SkillRegistry, default_skill_registry

__all__ = [
    "ActiveSkill",
    "DetectResult",
    "KNOWLEDGE_INDEX_VERSION",
    "Skill",
    "SkillRegistry",
    "default_skill_registry",
]
