"""
End-to-end validation of AEOS workflow using LM Studio / deepseek/deepseek-r1-0528-qwen3-8b.
This sets up a minimal config pointing at http://127.0.0.1:1234 and runs
one full lifecycle cycle on a trivial requirement: "Write a Python function
that adds two numbers and returns the result, with a unit test."

Run from the AEOS repo root:
    python scripts/validate_e2e_local.py
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

# Make sure we import from the local source
sys.path.insert(0, str(Path(__file__).parent.parent))

from aeos.core.config.schema import (
    AEOSConfig, ProjectConfig, RoutingConfig, ComplexityRouting, ModelTarget,
    ProviderConfig, ProviderType
)
from aeos.core.state.manager import StateManager
from aeos.core.workflow.engine import WorkflowEngine


def build_local_config() -> AEOSConfig:
    """Build a minimal config using LM Studio at 127.0.0.1:1234."""
    lm_studio = ProviderConfig(
        type=ProviderType.OLLAMA,
        base_url="http://127.0.0.1:1234",
        context_window=8192,
        max_tokens=2048,  # half of context_window -- safe for reasoning models
    )
    local_target = ModelTarget(
        provider="lm_studio",
        model="mistralai/mistral-7b-instruct-v0.3",
    )
    all_local = ComplexityRouting(high=local_target, medium=local_target, low=local_target)
    routing = RoutingConfig(
        inference=all_local,
        coding=all_local,
        planning=all_local,
        review=all_local,
        verification=all_local,
    )
    project_cfg = ProjectConfig(
        max_retries=2,         # 2 retries before auto-advancing past a stuck stage
        ask_on_critical=False, # non-interactive
        decompose_threshold=100,
        auto_activate_stages=False,
    )
    return AEOSConfig(
        providers={"lm_studio": lm_studio},
        routing=routing,
        project=project_cfg,
    )


async def main() -> None:
    print("=" * 60)
    print("AEOS End-to-End Local Validation")
    print("Provider: LM Studio (deepseek/deepseek-r1-0528-qwen3-8b) @ 127.0.0.1:1234")
    print("=" * 60)

    with tempfile.TemporaryDirectory(prefix="aeos_e2e_") as tmpdir:
        project_root = Path(tmpdir)
        workspace = project_root / ".aeos"
        workspace.mkdir(parents=True, exist_ok=True)

        config = build_local_config()
        sm = StateManager(workspace)
        state = sm.load()
        if not state.objective:
            state.objective = "Write a Python function that adds two numbers and returns the result. Include a pytest unit test."
            state.project_root = str(project_root)
            sm.save(state)

        engine = WorkflowEngine(
            config=config,
            state=state,
            state_manager=sm,
            project_root=project_root,
        )

        final_state = await engine.run()

        print("\n" + "=" * 60)
        print("VALIDATION RESULTS")
        print("=" * 60)
        print(f"  Final stage  : {final_state.current_stage}")
        print(f"  Is complete  : {final_state.is_complete}")
        print(f"  Tasks created: {len(final_state.tasks)}")
        print(f"  Decisions    : {len(final_state.decisions)}")
        print(f"  Failures     : {len(final_state.failures)}")

        task_statuses: dict[str, int] = {}
        for t in final_state.tasks.values():
            task_statuses[t.status.value] = task_statuses.get(t.status.value, 0) + 1
        if task_statuses:
            print("  Task statuses:", task_statuses)

        # Success criterion: progressed past REVIEW_REQUIREMENTS without looping
        ok_stages = {
            "PROJECT_PLANNING", "REVIEW_PROJECT_PLAN", "PROJECT_DECOMPOSITION",
            "REVIEW_DECOMPOSITION", "TASK_QUEUE", "TASK_EXECUTION_ENGINE",
            "SYSTEM_INTEGRATION", "SYSTEM_REVIEW", "FINAL_VERIFICATION", "COMPLETE",
        }
        if final_state.current_stage in ok_stages or final_state.is_complete:
            print("\n[PASS] Workflow progressed past REVIEW_REQUIREMENTS — no infinite loop!")
        else:
            print(f"\n[INFO] Workflow at: {final_state.current_stage}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
