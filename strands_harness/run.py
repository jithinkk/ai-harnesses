import asyncio

from strands_harness.human_in_the_loop import build_agent as build_hitl_agent
from strands_harness.orchestrator_workers import build_agent as build_ow_agent
from shared.trace import HitlTrace, OrchestratorTrace, run_demo, subtasks_from_report

DEFAULT_TASK = "Write a short product report covering pricing, onboarding, and support quality."
DEFAULT_MESSAGE_TASK = "Send a message to Alice: the report is ready."


def run_orchestrator_workers(task: str = DEFAULT_TASK) -> dict:
    """Dynamic fan-out to the `research` tool via Strands' Agents-as-Tools pattern."""
    agent = build_ow_agent()
    result = asyncio.run(agent.invoke_async(task))
    return {"final_output": str(result), "result": result}


def _pending_send_message(agent) -> dict | None:
    for message in agent.messages:
        for content in message["content"]:
            tool_use = content.get("toolUse")
            if tool_use and tool_use["name"] == "send_message":
                return tool_use
    return None


def run_human_in_the_loop(task: str = DEFAULT_MESSAGE_TASK, approve: bool = True) -> dict:
    """Runs to completion, auto-resolving any approval pause.

    Unlike the other harnesses, there's no separate resume call here: `build_agent`'s
    `HumanInTheLoop` intervention decides inline, during the single `invoke_async()`
    below, so `approve` is baked in up front rather than supplied after the fact.
    `send_message` is the only gated tool, so its presence in the conversation history
    afterward is how this reports `interrupted`, the same outcome the other harnesses
    report via a separate `interruptions`/`to_state()` value.
    """
    agent = build_hitl_agent(approve=approve)
    result = asyncio.run(agent.invoke_async(task))

    pending = _pending_send_message(agent)
    if pending is None:
        return {"interrupted": False, "result": result, "agent": agent}

    return {
        "interrupted": True,
        "pending": pending,
        "approved": approve,
        "result": result,
        "agent": agent,
    }


def main(task: str = DEFAULT_TASK) -> dict:
    return run_orchestrator_workers(task)


def describe_orchestrator_workers(task: str = DEFAULT_TASK) -> OrchestratorTrace:
    final = run_orchestrator_workers(task)["final_output"]
    return OrchestratorTrace(
        harness="strands",
        fanout_mechanism="Agents-as-Tools — a plain @tool runs a fresh Agent per call, one call per subtask",
        subtasks=subtasks_from_report(final),
        isolation="a new Agent() per research() call keeps each subagent's context isolated",
        final_report=final,
    )


def describe_human_in_the_loop() -> HitlTrace:
    outcome = run_human_in_the_loop()
    pending = outcome.get("pending") or {}
    return HitlTrace(
        harness="strands",
        gate_mechanism="HumanInTheLoop(allowed_tools=[...]) — an inverted, allow-list intervention",
        gated_tool=pending.get("name", "") if outcome["interrupted"] else "",
        gated_args=pending.get("input", {}) if outcome["interrupted"] else {},
        interrupted=outcome["interrupted"],
        approved=outcome.get("approved", False),
        resume_mechanism="decided inline by the `ask` callback wired in up front — no separate resume call",
        final_text=str(outcome["result"]),
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
