import asyncio

import pytest

pytest.importorskip("agent_framework")

from agent_framework import AgentSession  # noqa: E402

from agent_framework_harness.human_in_the_loop import build_agent as build_hitl_agent  # noqa: E402
from agent_framework_harness.orchestrator_workers import build_agent as build_ow_workflow  # noqa: E402
from agent_framework_harness.run import run_human_in_the_loop, run_orchestrator_workers  # noqa: E402


def _tool_contents(result) -> list[str]:
    outputs = []
    for message in result.messages:
        for content in message.contents:
            if content.type == "function_result":
                outputs.append(str(content.result))
    return outputs


def test_dynamic_fan_out_delegates_one_round_per_subtopic():
    """The count comes from the request at runtime, not from the workflow's participants."""
    report = run_orchestrator_workers("Write a report covering pricing, onboarding, and support quality.")

    final = report["final_output"]
    assert final.startswith("# Final Report")
    for topic in ("pricing", "onboarding", "support quality"):
        assert topic in final


def test_falls_back_to_default_topics_without_a_covering_clause():
    report = run_orchestrator_workers("Write a general product report.")

    final = report["final_output"]
    for topic in ("an overview", "key considerations"):
        assert topic in final


def test_returns_a_real_workflow():
    from agent_framework import Workflow

    assert isinstance(build_ow_workflow(), Workflow)


def test_pauses_before_a_side_effecting_tool_call():
    agent = build_hitl_agent()
    session = AgentSession()

    result = asyncio.run(agent.run("Send a message to Alice: report is ready", session=session))

    pending = [c for m in result.messages for c in m.contents if c.type == "function_approval_request"]
    assert pending
    assert not _tool_contents(result)


def test_approval_lets_the_tool_call_run():
    outcome = run_human_in_the_loop("Send a message to Alice: report is ready", approve=True)

    assert outcome["interrupted"] is True
    tool_messages = _tool_contents(outcome["result"])
    assert len(tool_messages) == 1
    assert "Message sent to Alice" in tool_messages[0]
    assert "Done:" in outcome["result"].text


def test_rejection_blocks_the_tool_call():
    outcome = run_human_in_the_loop("Send a message to Bob: budget approved", approve=False)

    tool_messages = _tool_contents(outcome["result"])
    assert len(tool_messages) == 1
    assert "rejected" in tool_messages[0].lower()
    assert "Message sent to Bob" not in tool_messages[0]
    assert "won't do that" in outcome["result"].text


def test_read_only_tools_skip_the_approval_gate():
    agent = build_hitl_agent()
    session = AgentSession()

    result = asyncio.run(agent.run("What is (12 + 8) * 3?", session=session))

    pending = [c for m in result.messages for c in m.contents if c.type == "function_approval_request"]
    assert not pending
    assert any(content == "60" for content in _tool_contents(result))
