from dotenv import load_dotenv

load_dotenv()

from langgraph.types import Command  # noqa: E402

from deepagents_harness.human_in_the_loop import build_agent as build_hitl_agent  # noqa: E402
from deepagents_harness.orchestrator_workers import build_agent as build_ow_agent  # noqa: E402

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


if __name__ == "__main__":
    import sys

    task = " ".join(sys.argv[1:]) or DEFAULT_TASK

    print("=== orchestrator_workers under deepagents ===\n")
    report = run_orchestrator_workers(task)
    for message in report["messages"]:
        role = message.__class__.__name__.replace("Message", "")
        if getattr(message, "tool_calls", None):
            delegated = ", ".join(call["args"].get("description", "") for call in message.tool_calls)
            print(f"[{role}] delegating to subagents: {delegated}")
        elif message.content:
            print(f"[{role}] {message.content}")

    print("\n=== human_in_the_loop under deepagents ===\n")
    outcome = run_human_in_the_loop()
    if not outcome["interrupted"]:
        print("No approval needed for this request.")
    else:
        requested = outcome["pending"]["action_requests"][0]
        print(f"Paused for approval: {requested['name']} {requested['args']}")
        print(f"Auto-{'approved' if outcome['approved'] else 'rejected'} for this demo run.\n")
        for message in outcome["result"]["messages"]:
            role = message.__class__.__name__.replace("Message", "")
            if message.content:
                print(f"[{role}] {message.content}")
