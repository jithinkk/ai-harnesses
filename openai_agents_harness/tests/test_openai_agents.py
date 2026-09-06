import pytest

pytest.importorskip("agents")

from agents import Agent  # noqa: E402

from openai_agents_harness.human_in_the_loop import build_agent as build_hitl_agent  # noqa: E402
from openai_agents_harness.orchestrator_workers import build_agent as build_ow_agent  # noqa: E402
from openai_agents_harness.run import run_human_in_the_loop, run_orchestrator_workers  # noqa: E402


def _tool_contents(result) -> list[str]:
    return [item.raw_item["output"] for item in result.new_items if getattr(item, "type", None) == "tool_call_output_item"]


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
    agent = build_hitl_agent()
    from agents import Runner
    import asyncio

    result = asyncio.run(Runner.run(agent, "Send a message to Alice: report is ready"))

    assert result.interruptions
    pending = result.interruptions[0]
    assert pending.tool_name == "send_message"
    # The tool must NOT have run yet.
    assert not _tool_contents(result)


def test_approval_lets_the_tool_call_run():
    outcome = run_human_in_the_loop("Send a message to Alice: report is ready", approve=True)

    assert outcome["interrupted"] is True
    tool_messages = _tool_contents(outcome["result"])
    assert len(tool_messages) == 1
    assert "Message sent to Alice" in tool_messages[0]
    assert "Done:" in outcome["result"].final_output


def test_rejection_blocks_the_tool_call():
    outcome = run_human_in_the_loop("Send a message to Bob: budget approved", approve=False)

    tool_messages = _tool_contents(outcome["result"])
    assert len(tool_messages) == 1
    assert "rejected" in tool_messages[0].lower()
    # The side effect genuinely never happened.
    assert "Message sent to Bob" not in tool_messages[0]
    assert "won't do that" in outcome["result"].final_output


def test_read_only_tools_skip_the_approval_gate():
    agent = build_hitl_agent()
    from agents import Runner
    import asyncio

    result = asyncio.run(Runner.run(agent, "What is (12 + 8) * 3?"))

    assert not result.interruptions
    assert any(content == "60" for content in _tool_contents(result))
