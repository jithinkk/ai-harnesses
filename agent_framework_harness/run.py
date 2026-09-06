import asyncio

from agent_framework import AgentSession, Message

from agent_framework_harness.human_in_the_loop import build_agent as build_hitl_agent
from agent_framework_harness.orchestrator_workers import build_agent as build_ow_workflow

DEFAULT_TASK = "Write a short product report covering pricing, onboarding, and support quality."
DEFAULT_MESSAGE_TASK = "Send a message to Alice: the report is ready."


def _pending_approval(result):
    for message in result.messages:
        for content in message.contents:
            if content.type == "function_approval_request":
                return content
    return None


def run_orchestrator_workers(task: str = DEFAULT_TASK) -> dict:
    """Dynamic fan-out to the `researcher` participant via Magentic orchestration."""
    workflow = build_ow_workflow()
    result = asyncio.run(workflow.run(task))
    outputs = result.get_outputs()
    final_text = outputs[0].text if outputs else ""
    return {"final_output": final_text, "result": result}


def run_human_in_the_loop(task: str = DEFAULT_MESSAGE_TASK, approve: bool = True) -> dict:
    """Runs to completion, auto-resolving any approval pause.

    A real UI would surface the pending `function_approval_request` to a human and only
    then resume. `AgentSession` plays the checkpointer's role here -- created once per
    call and threaded through both the initial run and the resume.
    """
    agent = build_hitl_agent()
    session = AgentSession()

    result = asyncio.run(agent.run(task, session=session))
    pending = _pending_approval(result)

    if pending is None:
        return {"interrupted": False, "result": result}

    response = pending.to_function_approval_response(approved=approve)
    resumed = asyncio.run(agent.run(Message(role="user", contents=[response]), session=session))
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

    print("=== orchestrator_workers under Microsoft Agent Framework ===\n")
    report = run_orchestrator_workers(task)
    print(report["final_output"])

    print("\n=== human_in_the_loop under Microsoft Agent Framework ===\n")
    outcome = run_human_in_the_loop()
    if not outcome["interrupted"]:
        print("No approval needed for this request.")
    else:
        call = outcome["pending"].function_call
        print(f"Paused for approval: {call.name} {call.arguments}")
        print(f"Auto-{'approved' if outcome['approved'] else 'rejected'} for this demo run.\n")
        print(outcome["result"].text)
