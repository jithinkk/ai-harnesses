import asyncio

from agents import Runner

from openai_agents_harness.human_in_the_loop import build_agent as build_hitl_agent
from openai_agents_harness.orchestrator_workers import build_agent as build_ow_agent

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


if __name__ == "__main__":
    import sys

    task = " ".join(sys.argv[1:]) or DEFAULT_TASK

    print("=== orchestrator_workers under the OpenAI Agents SDK ===\n")
    report = run_orchestrator_workers(task)
    print(report["final_output"])

    print("\n=== human_in_the_loop under the OpenAI Agents SDK ===\n")
    outcome = run_human_in_the_loop()
    if not outcome["interrupted"]:
        print("No approval needed for this request.")
    else:
        pending = outcome["pending"]
        print(f"Paused for approval: {pending.tool_name} {pending.arguments}")
        print(f"Auto-{'approved' if outcome['approved'] else 'rejected'} for this demo run.\n")
        print(outcome["result"].final_output)
