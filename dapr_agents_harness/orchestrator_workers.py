"""`orchestrator_workers`, expressed in Dapr Agents instead of vanilla LangGraph.

Same shape as
[`patterns/orchestrator_workers`](https://github.com/jithinkk/agentic-design-patterns/tree/main/patterns/orchestrator_workers):
an orchestrator decides at runtime how many independent subtasks a request needs, each
runs in its own isolated context, and the results are combined. The difference is who
owns the fan-out -- and, here, what runs it.

Dapr Agents' actual, first-class multi-agent primitive is `call_agent`/`trigger_agent`:
each agent is its own Dapr app/service, and one agent's workflow calls another's as a
*durable child workflow* across app boundaries -- genuinely distributed, matching Dapr's
actor-model philosophy. That's out of scope for this harness on purpose: every other
harness in this repo (this one included, for its `human_in_the_loop` half) runs as one
process against one sidecar, and standing up a second app/service just for this one
pattern would be a different, heavier kind of infrastructure than the sidecar exception
this repo already accepted. **Documented limitation, not a technical dead end** -- see
the README for the concrete cost.

What's implemented instead: a single `DurableAgent` whose `research` tool is called once
per subtopic in one turn -- the same Agents-as-Tools idiom every other harness in this
repo uses for this pattern, but running through Dapr's own durable Workflow engine
underneath (each tool call is a real, checkpointed workflow activity; the two calls
below actually execute concurrently and can complete in either order, verified against
the real sidecar rather than assumed).
"""

from __future__ import annotations

import json
import re

from dapr_agents import DurableAgent, tool
from dapr_agents.types.message import AssistantMessage, ToolCall

from dapr_agents_harness._fake_llm_client import PersistentFakeChatClient

# Deliberately duplicated from patterns/orchestrator_workers/nodes.py rather than
# imported: the two implementations are meant to be readable side by side without one
# depending on the other's internals.
_DEFAULT_TOPICS = ["an overview", "key considerations"]


def _extract_topics(task: str) -> list[str]:
    lowered = task.lower()
    marker = "covering"
    if marker not in lowered:
        return list(_DEFAULT_TOPICS)

    tail = task[lowered.index(marker) + len(marker) :].strip().rstrip(".")
    parts = re.split(r",| and ", tail)
    topics = [p.strip() for p in parts if p.strip()]
    return topics or list(_DEFAULT_TOPICS)


@tool
def research(topic: str) -> str:
    """Research one subtopic in isolation and report findings back."""
    return f"Findings on {topic}: three relevant points worth including in the report."


def _orchestrator_responder(messages) -> AssistantMessage:
    tool_outputs = [m.get("content") for m in messages if isinstance(m, dict) and m.get("role") == "tool"]
    if tool_outputs:
        return AssistantMessage(text="# Final Report\n\n" + "\n\n".join(tool_outputs))

    first_user = next((m.get("content") for m in messages if isinstance(m, dict) and m.get("role") == "user"), "")
    topics = _extract_topics(first_user)
    return AssistantMessage(
        content=None,
        tool_calls=[
            ToolCall(id=f"call_{i}", type="function", function={"name": "research", "arguments": json.dumps({"topic": topic})})
            for i, topic in enumerate(topics)
        ],
    )


def build_agent() -> DurableAgent:
    """Returns a `DurableAgent` that delegates to `research` -- one call per subtopic.

    Emitting several tool calls in one model turn is how Dapr Agents' workflow fans
    them out as concurrent activities, the direct analogue of returning several
    `Send`s from a conditional edge in the vanilla pattern.
    """
    return DurableAgent(
        name="orchestrator",
        role="assistant",
        llm=PersistentFakeChatClient(_orchestrator_responder),
        tools=[research],
    )
