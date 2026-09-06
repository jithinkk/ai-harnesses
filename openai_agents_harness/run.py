import asyncio
import json

from agents import Runner

from openai_agents_harness.human_in_the_loop import build_agent as build_hitl_agent
from openai_agents_harness.orchestrator_workers import build_agent as build_ow_agent
from shared.trace import HitlTrace, OrchestratorTrace, run_demo, subtasks_from_report

DEFAULT_TASK = "Write a short product report covering pricing, onboarding, and support quality."
DEFAULT_MESSAGE_TASK = "Send a message to Alice: the report is ready."


def run_orchestrator_workers(task: str = DEFAULT_TASK) -> dict:
    """Dynamic fan-out to subagents via the SDK's `Agent.as_tool()`."""
    agent = build_ow_agent()
    result = asyncio.run(Runner.run(agent, task))
    return {"final_output": result.final_output, "result": result}


def run_human_in_the_loop(task: str = DEFAULT_MESSAGE_TASK, approve: bool = True) -> dict:
    """Runs to completion, auto-resolving any approval pause.

    A real UI would surface the pending `ToolApprovalItem` to a human and only then
    resume. Unlike the vanilla/deepagents versions there's no `thread_id`/checkpointer to
    pass -- `result.to_state()` already carries everything needed to resume.
    """
    agent = build_hitl_agent()
    result = asyncio.run(Runner.run(agent, task))

    if not result.interruptions:
        return {"interrupted": False, "result": result}

    pending = result.interruptions[0]
    state = result.to_state()
    if approve:
        state.approve(pending)
    else:
        state.reject(pending, rejection_message="Rejected by human review.")

    resumed = asyncio.run(Runner.run(agent, state))
    return {
        "interrupted": True,
        "pending": pending,
        "approved": approve,
        "result": resumed,
    }


def main(task: str = DEFAULT_TASK) -> dict:
    return run_orchestrator_workers(task)


def _as_dict(arguments) -> dict:
    if isinstance(arguments, dict):
        return arguments
    try:
        return json.loads(arguments)
    except (TypeError, ValueError):
        return {"arguments": arguments}


def describe_orchestrator_workers(task: str = DEFAULT_TASK) -> OrchestratorTrace:
    final = run_orchestrator_workers(task)["final_output"]
    return OrchestratorTrace(
        harness="openai-agents",
        fanout_mechanism="Agent.as_tool() — specialist agent wrapped as a callable tool, one call per subtask",
        subtasks=subtasks_from_report(final),
        isolation="as_tool() invokes the subagent with generated input in its own run",
        final_report=final,
    )


def describe_human_in_the_loop() -> HitlTrace:
    outcome = run_human_in_the_loop()
    pending = outcome.get("pending")
    return HitlTrace(
        harness="openai-agents",
        gate_mechanism="needs_approval on the tool → RunResult.interruptions (ToolApprovalItem)",
        gated_tool=getattr(pending, "tool_name", "") if outcome["interrupted"] else "",
        gated_args=_as_dict(getattr(pending, "arguments", {})) if outcome["interrupted"] else {},
        interrupted=outcome["interrupted"],
        approved=outcome.get("approved", False),
        resume_mechanism="RunState.approve()/.reject(), then re-run Runner.run(agent, state)",
        final_text=getattr(outcome["result"], "final_output", ""),
        durable=False,
    )


if __name__ == "__main__":
    import sys

    run_demo(
        sys.argv[1:],
        DEFAULT_TASK,
        describe_ow=describe_orchestrator_workers,
        describe_hitl=describe_human_in_the_loop,
    )
