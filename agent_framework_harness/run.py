import asyncio
import json

from agent_framework import AgentSession, Message

from agent_framework_harness.human_in_the_loop import build_agent as build_hitl_agent
from agent_framework_harness.orchestrator_workers import build_agent as build_ow_workflow
from shared.trace import HitlTrace, OrchestratorTrace, run_demo, subtasks_from_report

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
        harness="agent-framework",
        fanout_mechanism="Magentic orchestration — a manager decides who acts next each round via a progress ledger",
        subtasks=subtasks_from_report(final),
        isolation="each researcher round runs as its own participant turn",
        final_report=final,
    )


def describe_human_in_the_loop() -> HitlTrace:
    outcome = run_human_in_the_loop()
    call = outcome["pending"].function_call if outcome["interrupted"] else None
    return HitlTrace(
        harness="agent-framework",
        gate_mechanism="RequestInfoExecutor pause on a function_approval_request",
        gated_tool=getattr(call, "name", "") if call else "",
        gated_args=_as_dict(getattr(call, "arguments", {})) if call else {},
        interrupted=outcome["interrupted"],
        approved=outcome.get("approved", False),
        resume_mechanism="external response threaded back through the same AgentSession, then agent.run(...) again",
        final_text=getattr(outcome["result"], "text", ""),
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
