"""`orchestrator_workers`, expressed in the Strands Agents SDK instead of vanilla LangGraph.

Same shape as
[`patterns/orchestrator_workers`](https://github.com/jithinkk/agentic-design-patterns/tree/main/patterns/orchestrator_workers):
an orchestrator decides at runtime how many independent subtasks a request needs, each
runs in its own isolated context, and the results are combined. The difference is who
owns the fan-out.

Strands actually ships three multi-agent patterns -- Graph, Swarm, and Agents-as-Tools --
and only one fits here. **Graph** is a deterministic directed graph with edges fixed at
build time, which makes it `parallelization`'s shape, not this one. **Swarm** is a
peer-to-peer relay: agents hand off the whole conversation to each other via an injected
`handoff_to_agent` tool, and whichever agent's turn ends without a further handoff
produces the swarm's answer. That's a genuinely different collaboration model from
"dispatch N independent subtasks, collect N results, synthesize" -- more suited to
open-ended team hand-offs than a fixed dispatch-and-collect shape, and its stateful
turn-passing made it the least reliable of the three to script deterministically for this
demo. **Agents-as-Tools** -- wrapping a subagent call inside a plain `@tool` function --
is the closest analogue to deepagents' `task` tool and the other harnesses'
`Agent.as_tool()`/`.as_tool()`-equivalents: the orchestrator calls `research` as many
times as it likes in one turn, each call runs the researcher agent in isolation, and the
result comes back as a normal tool result the orchestrator reads.
"""

from __future__ import annotations

import re

from strands import Agent, tool

from strands_harness._fake_model import PersistentFakeModel

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


def _researcher_responder(messages):
    last_user = next((m for m in reversed(messages) if m["role"] == "user"), None)
    subtopic = last_user["content"][0].get("text", "the topic") if last_user else "the topic"
    return [{"text": f"Findings on {subtopic}: three relevant points worth including in the report."}]


# One shared fake model backs every `research(...)` call -- a fresh `Agent` per call
# (see `research` below) keeps each subagent invocation's context isolated, the same
# guarantee deepagents' `task` tool and the other harnesses' subagent delegation give.
_researcher_model = PersistentFakeModel(_researcher_responder)


@tool
def research(topic: str) -> str:
    """Research one subtopic in isolation and report findings back."""
    researcher = Agent(model=_researcher_model)
    return str(researcher(topic))


def _orchestrator_responder(messages):
    tool_outputs = [
        content["toolResult"]["content"][0]["text"]
        for message in messages
        for content in message["content"]
        if "toolResult" in content
    ]
    if tool_outputs:
        return [{"text": "# Final Report\n\n" + "\n\n".join(tool_outputs)}]

    first_user = next((m for m in messages if m["role"] == "user"), None)
    task = first_user["content"][0].get("text", "") if first_user else ""
    topics = _extract_topics(task)
    return [
        {"toolUse": {"toolUseId": f"call_{i}", "name": "research", "input": {"topic": topic}}}
        for i, topic in enumerate(topics)
    ]


def build_agent() -> Agent:
    """Returns an `Agent` that delegates to `research` -- one call per subtopic.

    Emitting several `toolUse` blocks in one model turn is how Strands runs them
    concurrently, the direct analogue of returning several `Send`s from a conditional
    edge in the vanilla pattern.
    """
    return Agent(model=PersistentFakeModel(_orchestrator_responder), tools=[research])
