import json

import pytest

pytest.importorskip("dapr_agents")

from dapr_agents import DurableAgent  # noqa: E402

from dapr_agents_harness.orchestrator_workers import build_agent as build_ow_agent  # noqa: E402
from dapr_agents_harness.run import run_human_in_the_loop, run_orchestrator_workers  # noqa: E402


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


def test_returns_a_real_durable_agent():
    assert isinstance(build_ow_agent(), DurableAgent)


def test_pauses_before_a_side_effecting_tool_call_then_approval_lets_it_run():
    outcome = run_human_in_the_loop("Send a message to Alice: report is ready", approve=True)

    assert outcome["interrupted"] is True
    assert outcome["pending"]["tool_name"] == "send_message"
    assert outcome["pending"]["tool_arguments"]["recipient"] == "Alice"

    final = json.loads(outcome["result"])["content"]
    assert "Done:" in final
    assert "Message sent to Alice" in final


def test_rejection_blocks_the_tool_call():
    outcome = run_human_in_the_loop("Send a message to Bob: budget approved", approve=False)

    assert outcome["interrupted"] is True
    final = json.loads(outcome["result"])["content"]
    # The side effect genuinely never happened.
    assert "Message sent to Bob" not in final
    assert "won't do that" in final


def test_read_only_tools_skip_the_approval_gate():
    outcome = run_human_in_the_loop("What is (12 + 8) * 3?", approve=False)

    assert outcome["interrupted"] is False
    final = json.loads(outcome["result"])["content"]
    assert final == "Done: 60"
