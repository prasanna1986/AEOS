"""Base agent -- prompt rendering + LLM call + JSON extraction."""

from __future__ import annotations

import json
import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from aeos.core.config.schema import Complexity, TaskType
from aeos.core.providers.router import ModelRouter
from aeos.core.providers.base import Message

# Locate the prompts directory relative to this file
_PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts"


def _get_jinja_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_PROMPTS_DIR)),
        autoescape=select_autoescape(disabled_extensions=("j2",)),
        trim_blocks=True,
        lstrip_blocks=True,
    )


class BaseAgent:
    """
    Base class for all AEOS agents.

    Provides:
    - Jinja2 prompt rendering
    - System prompt injection
    - LLM call via ModelRouter
    - JSON extraction from markdown-fenced responses
    """

    prompt_template: str = "system.j2"
    task_type: TaskType = TaskType.INFERENCE
    complexity: Complexity = Complexity.MEDIUM

    def __init__(self, router: ModelRouter, project_context: dict) -> None:
        self._router = router
        self._ctx = project_context  # project-level template variables
        self._jinja = _get_jinja_env()

    def _render(self, template_name: str, **kwargs) -> str:
        tmpl = self._jinja.get_template(template_name)
        return tmpl.render(**{**self._ctx, **kwargs})

    def _render_system(self, **kwargs) -> str:
        return self._render("system.j2", **kwargs)

    async def _call(
        self,
        user_prompt: str,
        system_override: str | None = None,
        task_type: TaskType | None = None,
        complexity: Complexity | None = None,
        temperature: float = 0.2,
    ) -> str:
        system = system_override or self._render_system()
        messages = [
            Message(role="system", content=system),
            Message(role="user", content=user_prompt),
        ]
        response = await self._router.complete(
            messages=messages,
            task_type=task_type or self.task_type,
            complexity=complexity or self.complexity,
            temperature=temperature,
        )
        return response.content

    @staticmethod
    def extract_json(text: str) -> dict | list:
        """
        Extract the first JSON object or array from a response that may
        contain markdown fences, prose, or other formatting.
        """
        # Try fenced code blocks first
        fenced = re.search(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", text, re.DOTALL)
        if fenced:
            return json.loads(fenced.group(1))
        # Try bare JSON
        bare = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
        if bare:
            return json.loads(bare.group(1))
        raise ValueError(f"No JSON found in response:\n{text[:500]}")
