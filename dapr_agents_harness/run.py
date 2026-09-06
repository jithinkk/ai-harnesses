import asyncio
import json

from dapr_agents.workflow.runners.agent import AgentRunner

from dapr_agents_harness.human_in_the_loop import build_agent as build_hitl_agent
from dapr_agents_harness.orchestrator_workers import build_agent as build_ow_agent
from shared.trace import HitlTrace, OrchestratorTrace, run_demo, subtasks_from_report

DEFAULT_TASK = "Write a short product report covering pricing, onboarding, and support quality."
DEFAULT_MESSAGE_TASK = "Send a message to Alice: the report is ready."


def run_orchestrator_workers(task: str = DEFAULT_TASK) -> dict:
    """Dynamic fan-out to the `research` tool, run as a real durable workflow."""
    agent = build_ow_agent()
    runner = AgentRunner()
    output = runner.run_sync(agent, {"task": task})
    final_output = json.loads(output)["content"] if output else ""
    return {"final_output": final_output, "result": output}


async def _run_human_in_the_loop_async(task: str, approve: bool) -> dict:
    agent = build_hitl_agent()
    runner = AgentRunner()

    instance_id = await runner.run(agent, {"task": task}, wait=False)

    pending = None
    for _ in range(30):
        await asyncio.sleep(1)
        approvals = agent.list_pending_approvals()
        if approvals:
            pending = approvals[0]
            break

    if pending is None:
        state = runner.wait_for_workflow_completion(instance_id)
        output = state.serialized_output if state else None
        return {"interrupted": False, "result": output}

    reason = None if approve else "Rejected by human review."
    agent.raise_approval_event(instance_id, pending["approval_request_id"], approved=approve, reason=reason)

    state = runner.wait_for_workflow_completion(instance_id)
    output = state.serialized_output if state else None
    return {
        "interrupted": True,
        "pending": pending,
        "approved": approve,
        "result": output,
    }


def run_human_in_the_loop(task: str = DEFAULT_MESSAGE_TASK, approve: bool = True) -> dict:
    """Runs to completion, auto-resolving any approval pause.

    A real UI would surface `pending` to a human (via pub/sub or the `GET
    /hitl/approvals` HTTP endpoint in `serve()` mode) and only then call
    `agent.raise_approval_event(...)`. Unlike the checkpointer-based harnesses, the
    pause here is a real suspended durable workflow instance, not an in-memory one --
    `instance_id` is what a separate process would need to resume it, the same role
    `thread_id` plays for the LangGraph-based harnesses.
    """
    return asyncio.run(_run_human_in_the_loop_async(task, approve))


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
        harness="dapr-agents",
        fanout_mechanism="one DurableAgent's `research` tool, called once per subtopic as durable workflow activities",
        subtasks=subtasks_from_report(final),
        isolation="each tool call is a separate checkpointed workflow activity",
        final_report=final,
    )


def describe_human_in_the_loop() -> HitlTrace:
    outcome = run_human_in_the_loop()
    pending = outcome.get("pending") or {}
    final_text = ""
    if outcome.get("result"):
        try:
            final_text = json.loads(outcome["result"])["content"]
        except (TypeError, ValueError, KeyError):
            final_text = str(outcome["result"])
    return HitlTrace(
        harness="dapr-agents",
        gate_mechanism="a before_tool_call hook returns RequireApproval(...); the workflow suspends on wait_for_external_event",
        gated_tool=pending.get("tool_name", "") if outcome["interrupted"] else "",
        gated_args=_as_dict(pending.get("tool_arguments", {})) if outcome["interrupted"] else {},
        interrupted=outcome["interrupted"],
        approved=outcome.get("approved", False),
        resume_mechanism="raise_approval_event(instance_id, request_id, approved=...) — a durable suspended instance",
        final_text=final_text,
        durable=True,
    )


if __name__ == "__main__":
    import sys

    run_demo(
        sys.argv[1:],
        DEFAULT_TASK,
        describe_ow=describe_orchestrator_workers,
        describe_hitl=describe_human_in_the_loop,
    )
