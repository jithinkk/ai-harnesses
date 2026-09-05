import pytest

# `deepagents` is a plain, non-optional dependency of this repo, so this
# should always resolve; `importorskip` is kept anyway so a partial/minimal
# environment degrades to a skip rather than a collection error.
pytest.importorskip("deepagents")

from langgraph.types import Command  # noqa: E402

from deepagents_harness.human_in_the_loop import build_agent as build_hitl_agent  # noqa: E402
from deepagents_harness.orchestrator_workers import build_agent as build_ow_agent  # noqa: E402
from deepagents_harness.run import run_human_in_the_loop, run_orchestrator_workers  # noqa: E402


def _tool_contents(result) -> list[str]:
    return [m.content for m in result["messages"] if m.type == "tool"]


def test_dynamic_fan_out_delegates_one_subagent_call_per_subtopic():
    """The count comes from the request at runtime, not from the graph."""
    result = run_orchestrator_workers("Write a report covering pricing, onboarding, and support quality.")

    delegations = [
        call
        for m in result["messages"]
        for call in (getattr(m, "tool_calls", None) or [])
        if call["name"] == "task"
    ]
    assert [c["args"]["description"] for c in delegations] == ["pricing", "onboarding", "support quality"]
    assert all(c["args"]["subagent_type"] == "researcher" for c in delegations)

    # Every subtopic came back with findings, and they reached the report.
    assert len(_tool_contents(result)) == 3
    final = result["messages"][-1].content
    assert final.startswith("# Final Report")
    for topic in ("pricing", "onboarding", "support quality"):
        assert topic in final


def test_falls_back_to_default_topics_without_a_covering_clause():
    result = run_orchestrator_workers("Write a general product report.")

    delegations = [
        call
        for m in result["messages"]
        for call in (getattr(m, "tool_calls", None) or [])
        if call["name"] == "task"
    ]
    assert [c["args"]["description"] for c in delegations] == ["an overview", "key considerations"]


def test_returns_a_real_langgraph_compiled_graph():
    """deepagents is a layer on LangGraph, not a replacement for it.

    This is what makes the comparison fair: the same `.invoke()`, the same
    checkpointer contract, the same recursion_limit config as the vanilla
    patterns.
    """
    from langgraph.graph.state import CompiledStateGraph

    assert isinstance(build_ow_agent(), CompiledStateGraph)


def test_pauses_before_a_side_effecting_tool_call():
    agent = build_hitl_agent()
    config = {"configurable": {"thread_id": "da-pause-test"}}

    result = agent.invoke({"messages": [("user", "Send a message to Alice: report is ready")]}, config)

    assert "__interrupt__" in result
    pending = result["__interrupt__"][0].value
    requested = pending["action_requests"][0]
    assert requested["name"] == "send_message"
    assert requested["args"]["recipient"] == "Alice"
    # The tool must NOT have run yet.
    assert not _tool_contents(result)


def test_approval_lets_the_tool_call_run():
    outcome = run_human_in_the_loop(
        "Send a message to Alice: report is ready", approve=True, thread_id="da-approve-test"
    )

    assert outcome["interrupted"] is True
    tool_messages = _tool_contents(outcome["result"])
    assert len(tool_messages) == 1
    assert "Message sent to Alice" in tool_messages[0]
    assert "Done:" in outcome["result"]["messages"][-1].content


def test_rejection_blocks_the_tool_call():
    outcome = run_human_in_the_loop(
        "Send a message to Bob: budget approved", approve=False, thread_id="da-reject-test"
    )

    tool_messages = _tool_contents(outcome["result"])
    assert len(tool_messages) == 1
    assert "rejected" in tool_messages[0].lower()
    # The side effect genuinely never happened.
    assert not any("Message sent to Bob" in m.content for m in outcome["result"]["messages"])
    assert "won't do that" in outcome["result"]["messages"][-1].content


def test_read_only_tools_skip_the_approval_gate():
    agent = build_hitl_agent()
    config = {"configurable": {"thread_id": "da-no-gate-test"}}

    result = agent.invoke({"messages": [("user", "What is (12 + 8) * 3?")]}, config)

    assert "__interrupt__" not in result
    assert any(content == "60" for content in _tool_contents(result))
