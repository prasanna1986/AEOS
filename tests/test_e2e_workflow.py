"""
Deterministic E2E integration tests for AEOS WorkflowEngine.
No LM Studio / GPU required — mocks are injected at the router level.
"""
from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

import pytest

from aeos.core.config.schema import (
    AEOSConfig, ComplexityRouting, ModelTarget, ProjectConfig,
    ProviderConfig, ProviderType, RoutingConfig,
)
from aeos.core.providers.base import CompletionRequest, CompletionResponse
from aeos.core.state.manager import StateManager
from aeos.core.workflow.engine import WorkflowEngine


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _config() -> AEOSConfig:
    t = ModelTarget(provider="mock", model="mock-model")
    cr = ComplexityRouting(high=t, medium=t, low=t)
    return AEOSConfig(
        providers={"mock": ProviderConfig(type=ProviderType.OLLAMA, base_url="http://mock")},
        routing=RoutingConfig(inference=cr, coding=cr, planning=cr, review=cr, verification=cr),
        project=ProjectConfig(
            max_retries=2, ask_on_critical=False,
            decompose_threshold=100, auto_activate_stages=False,
        ),
    )


def _review_pass() -> str:
    return json.dumps({
        "outcome": "pass", "confidence": 0.9, "summary": "OK.",
        "issues": [], "strengths": [], "next_action": "proceed",
        "questions_for_user": [],
    })


def _requirements_understood() -> str:
    return json.dumps({
        "understood": True, "summary": "Add two numbers with pytest test.",
        "clarity_score": 0.95, "gaps": [],
    })


def _plan() -> str:
    return json.dumps({
        "summary": "Implement add function with test",
        "milestones": [{
            "id": "m1", "title": "Implementation",
            "tasks": [{
                "id": "t1", "title": "Write add() function",
                "description": "add(a,b)->a+b", "objective": "Create add",
                "complexity": "low", "task_type": "coding", "priority": 10,
            }],
        }],
    })


def _patch_router(engine: WorkflowEngine, responses: list[str]) -> None:
    """Patch ModelRouter.complete directly — bypasses provider cache and retry wrappers."""
    call_count = 0

    async def _mock_complete(messages, task_type, complexity, temperature=0.2, max_tokens=2048):
        nonlocal call_count
        resp = responses[min(call_count, len(responses) - 1)]
        call_count += 1
        return CompletionResponse(content=resp, model="mock", provider="mock", raw={})

    engine._router.complete = _mock_complete


# ---------------------------------------------------------------------------
# Test 1: happy-path mock flow
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_engine_full_flow_mock():
    """Workflow progresses past REVIEW_REQUIREMENTS and reaches PROJECT_PLANNING."""
    with tempfile.TemporaryDirectory(prefix="aeos_e2e_") as tmpdir:
        workspace = Path(tmpdir) / ".aeos"
        workspace.mkdir(parents=True)
        config = _config()
        sm = StateManager(workspace)
        state = sm.load()
        state.objective = "Write a Python function that adds two numbers, with a pytest test."
        state.project_root = str(Path(tmpdir))
        sm.save(state)

        engine = WorkflowEngine(config=config, state=state, state_manager=sm,
                                project_root=Path(tmpdir))

        _patch_router(engine, [
            _requirements_understood(),  # UNDERSTAND_REQUIREMENTS
            _review_pass(),              # REVIEW_REQUIREMENTS
            _plan(),                     # PROJECT_PLANNING
            _review_pass(),              # REVIEW_PROJECT_PLAN
            _review_pass(),              # REVIEW_DECOMPOSITION
        ])

        stages_seen: list[str] = []
        orig = engine._execute_stage

        async def capped(stage):
            stages_seen.append(stage.value)
            if len(stages_seen) >= 20:
                from aeos.core.workflow.stages import WorkflowStage
                return WorkflowStage.COMPLETE
            return await orig(stage)

        engine._execute_stage = capped
        await engine.run()

        assert "UNDERSTAND_REQUIREMENTS" in stages_seen
        assert "REVIEW_REQUIREMENTS" in stages_seen
        assert "PROJECT_PLANNING" in stages_seen

        rr_count = stages_seen.count("REVIEW_REQUIREMENTS")
        assert rr_count <= config.project.max_retries + 1, \
            f"REVIEW_REQUIREMENTS visited {rr_count}x -- circuit breaker failed"

        pp_idx = stages_seen.index("PROJECT_PLANNING")
        rr_last = max(i for i, s in enumerate(stages_seen) if s == "REVIEW_REQUIREMENTS")
        assert pp_idx > rr_last, "PROJECT_PLANNING must follow REVIEW_REQUIREMENTS"


# ---------------------------------------------------------------------------
# Test 2: circuit breaker with simulated HTTP errors
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_circuit_breaker_on_http_errors():
    """
    Every LLM stage raises. Circuit breaker must:
    - Visit each failing stage at most max_retries times per continuous run
    - Auto-advance past each stuck stage
    - Reach COMPLETE without hanging
    """
    with tempfile.TemporaryDirectory(prefix="aeos_cb_") as tmpdir:
        workspace = Path(tmpdir) / ".aeos"
        workspace.mkdir(parents=True)
        config = _config()
        config.project.max_retries = 2
        sm = StateManager(workspace)
        state = sm.load()
        state.objective = "Test circuit breaker"
        state.project_root = str(Path(tmpdir))
        sm.save(state)

        engine = WorkflowEngine(config=config, state=state, state_manager=sm,
                                project_root=Path(tmpdir))

        LLM_STAGES = {
            "UNDERSTAND_REQUIREMENTS", "REVIEW_REQUIREMENTS", "PROJECT_PLANNING",
            "REVIEW_PROJECT_PLAN", "REVIEW_DECOMPOSITION", "SYSTEM_REVIEW",
        }

        stages_seen: list[str] = []
        orig = engine._execute_stage

        async def injected(stage):
            stages_seen.append(stage.value)
            if len(stages_seen) >= 30:
                from aeos.core.workflow.stages import WorkflowStage
                return WorkflowStage.COMPLETE
            if stage.value in LLM_STAGES:
                raise ConnectionError(f"Simulated HTTP 400 for {stage.value}")
            return await orig(stage)

        engine._execute_stage = injected
        await engine.run()

        # Each stage may appear up to max_retries times PER contiguous block.
        # Count max consecutive visits to the same stage (not total).
        max_consecutive = 1
        current_run = 1
        for i in range(1, len(stages_seen)):
            if stages_seen[i] == stages_seen[i - 1]:
                current_run += 1
                max_consecutive = max(max_consecutive, current_run)
            else:
                current_run = 1

        assert max_consecutive <= config.project.max_retries, \
            f"Max consecutive stage visits was {max_consecutive}, expected <= {config.project.max_retries}"

        unique = list(dict.fromkeys(stages_seen))
        assert len(unique) >= 5, f"Too few unique stages reached: {unique}"
        print(f"\nUnique stages: {unique}")
        print(f"Max consecutive same-stage visits: {max_consecutive}")
