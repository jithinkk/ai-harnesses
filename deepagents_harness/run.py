from dotenv import load_dotenv

load_dotenv()

from langgraph.types import Command  # noqa: E402

from deepagents_harness.human_in_the_loop import build_agent as build_hitl_agent  # noqa: E402
from deepagents_harness.orchestrator_workers import build_agent as build_ow_agent  # noqa: E402
from shared.trace import HitlTrace, OrchestratorTrace, run_demo  # noqa: E402

DEFAULT_TASK = "Write a short product report covering pricing, onboarding, and support quality."
DEFAULT_MESSAGE_TASK = "Send a message to Alice: the report is ready."

# Same reasoning as the vanilla patterns' run.py: LangGraph's own default,
# made an explicit, overridable choice rather than an implicit one.
DEFAULT_RECURSION_LIMIT = 25


def run_orchestrator_workers(task: str = DEFAULT_TASK, recursion_limit: int = DEFAULT_RECURSION_LIMIT) -> dict:
    """Dynamic fan-out to subagents via deepagents' built-in `task` tool."""
    agent = build_ow_agent()
    return agent.invoke(
        {"messages": [("user", task)]},
        config={"recursion_limit": recursion_limit},
    )


def run_human_in_the_loop(
    task: str = DEFAULT_MESSAGE_TASK,
    approve: bool = True,
    thread_id: str = "demo",
    recursion_limit: int = DEFAULT_RECURSION_LIMIT,
) -> dict:
    """Runs to completion, auto-resolving any approval pause.

    A real UI would surface `pending` to a human and only then resume. Note
    the resume payload differs from the vanilla pattern's bare
    `Command(resume=True)` -- deepagents expects a decisions envelope, and
    supports `edit`/`respond` besides `approve`/`reject`.
    """
    agent = build_hitl_agent()
    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": recursion_limit}

    result = agent.invoke({"messages": [("user", task)]}, config)
    pending_interrupts = result.get("__interrupt__")

    if not pending_interrupts:
        return {"interrupted": False, "result": result}

    decision = {"type": "approve"} if approve else {"type": "reject"}
    resumed = agent.invoke(Command(resume={"decisions": [decision]}), config)
    return {
        "interrupted": True,
        "pending": pending_interrupts[0].value,
        "approved": approve,
        "result": resumed,
    }


def main(task: str = DEFAULT_TASK) -> dict:
    return run_orchestrator_workers(task)


def describe_orchestrator_workers(task: str = DEFAULT_TASK) -> OrchestratorTrace:
    """Adapt deepagents' LangGraph state into the shared trace vocabulary."""
    report = run_orchestrator_workers(task)
    delegated = [
        call["args"].get("description", "")
        for m in report["messages"]
        for call in (getattr(m, "tool_calls", None) or [])
        if call["name"] == "task"
    ]
    final = next((m.content for m in reversed(report["messages"]) if m.content), "")
    return OrchestratorTrace(
        harness="deepagents",
        fanout_mechanism="built-in `task` tool — model emits one call per subtask",
        subtasks=delegated,
        isolation="each `task` runs statelessly in a fresh context window",
        final_report=final,
    )


def describe_human_in_the_loop() -> HitlTrace:
    outcome = run_human_in_the_loop()
    requested = outcome["pending"]["action_requests"][0] if outcome["interrupted"] else {}
    final = next((m.content for m in reversed(outcome["result"]["messages"]) if m.content), "")
    return HitlTrace(
        harness="deepagents",
        gate_mechanism='interrupt_on={"send_message": True} — LangGraph interrupt() + a checkpointer',
        gated_tool=requested.get("name", ""),
        gated_args=requested.get("args", {}),
        interrupted=outcome["interrupted"],
        approved=outcome.get("approved", False),
        resume_mechanism='separate invoke(Command(resume={"decisions": [{"type": "approve"}]}))',
        final_text=final,
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
