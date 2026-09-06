import asyncio

import pytest

pytest.importorskip("strands")

from strands import Agent  # noqa: E402

from strands_harness.human_in_the_loop import build_agent as build_hitl_agent  # noqa: E402
from strands_harness.orchestrator_workers import build_agent as build_ow_agent  # noqa: E402
from strands_harness.run import run_human_in_the_loop, run_orchestrator_workers  # noqa: E402


def _tool_contents(agent) -> list[str]:
    return [
        content["toolResult"]["content"][0]["text"]
        for message in agent.messages
        for content in message["content"]
        if "toolResult" in content
    ]


def test_dynamic_fan_out_delegates_one_call_per_subtopic():
    """The count comes from the request at runtime, not from the agent's tool list."""
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


def test_returns_a_real_agent():
    assert isinstance(build_ow_agent(), Agent)


def test_pauses_before_a_side_effecting_tool_call():
    agent = build_hitl_agent(approve=False)
    asyncio.run(agent.invoke_async("Send a message to Alice: report is ready"))

    # The tool must NOT have actually run -- only a confirmation-failure result.
    tool_messages = _tool_contents(agent)
    assert len(tool_messages) == 1
    assert "Message sent to Alice" not in tool_messages[0]


def test_approval_lets_the_tool_call_run():
    outcome = run_human_in_the_loop("Send a message to Alice: report is ready", approve=True)

    assert outcome["interrupted"] is True
    tool_messages = _tool_contents(outcome["agent"])
    assert len(tool_messages) == 1
    assert "Message sent to Alice" in tool_messages[0]
    assert "Done:" in str(outcome["result"])


def test_rejection_blocks_the_tool_call():
    outcome = run_human_in_the_loop("Send a message to Bob: budget approved", approve=False)

    assert outcome["interrupted"] is True
    tool_messages = _tool_contents(outcome["agent"])
    assert len(tool_messages) == 1
    # The side effect genuinely never happened.
    assert "Message sent to Bob" not in tool_messages[0]
    assert "won't do that" in str(outcome["result"])


def test_read_only_tools_skip_the_approval_gate():
    agent = build_hitl_agent(approve=False)

    result = asyncio.run(agent.invoke_async("What is (12 + 8) * 3?"))

    assert any(content == "60" for content in _tool_contents(agent))
    assert str(result).strip() == "Done: 60"
