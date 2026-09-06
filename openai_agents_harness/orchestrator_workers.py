"""`orchestrator_workers`, expressed in the OpenAI Agents SDK instead of vanilla LangGraph.

Same shape as
[`patterns/orchestrator_workers`](https://github.com/jithinkk/agentic-design-patterns/tree/main/patterns/orchestrator_workers):
an orchestrator decides at runtime how many independent subtasks a request needs, each
runs in its own isolated context, and the results are combined. The difference is who
owns the fan-out.

Vanilla LangGraph makes it explicit: `continue_to_workers` returns one `Send("worker",
...)` per subtask, a `worker` node handles each, and an `operator.add` reducer
accumulates results before `synthesizer` runs. You write the fan-out, so you can see and
test every edge of it.

The Agents SDK hands you `Agent.as_tool()`: wrap a specialist agent as a callable tool of
an orchestrator agent, and the model delegates by calling that tool -- once per subtask,
as many times as it likes in one turn. This is deliberately not a "handoff" (the SDK's
other multi-agent primitive): a handoff transfers the *whole conversation* to exactly one
other agent; `as_tool()` calls a subagent with *generated input* and returns control to
the caller, which is what a fan-out needs.
"""

from __future__ import annotations

import re

from agents import Agent
from agents.testing.model import assistant_message, function_call

from openai_agents_harness._fake_model import PersistentFakeModel

# Marker in the researcher subagent's instructions, so the one scripted responder can
# tell an orchestrator turn from a subagent turn. Same idiom
# `deepagents_harness/orchestrator_workers.py` uses for the same reason.
_RESEARCHER_MARKER = "STAGE: WORKER"

ORCHESTRATOR_INSTRUCTIONS = (
    "You coordinate research. Break the request into independent subtopics and delegate "
    "each one to the `research` tool, then combine what comes back into one report."
)

RESEARCHER_INSTRUCTIONS = f"{_RESEARCHER_MARKER}. Research the single subtopic you are given and report findings."

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


def _fake_responder(system_instructions, input):
    # A researcher subagent turn: `as_tool()` runs it with its own instructions in a
    # fresh input list, so the marker is how we recognise it.
    if system_instructions and _RESEARCHER_MARKER in system_instructions:
        subtopic = next((i.get("content") for i in reversed(input) if i.get("role") == "user"), "")
        return [assistant_message(f"Findings on {subtopic}: three relevant points worth including in the report.")]

    # An orchestrator turn. If results are already back, synthesise; otherwise fan out
    # with one `research` call per subtopic. Emitting several tool calls in one message
    # is how the SDK runs them concurrently -- the direct analogue of returning several
    # `Send`s from a conditional edge.
    tool_outputs = [i for i in input if i.get("type") == "function_call_output"]
    if tool_outputs:
        report = "\n\n".join(o["output"] for o in tool_outputs)
        return [assistant_message(f"# Final Report\n\n{report}")]

    first_user = next((i.get("content") for i in input if i.get("role") == "user"), "")
    topics = _extract_topics(first_user)
    return [
        function_call("research", {"input": topic}, call_id=f"call_{i}") for i, topic in enumerate(topics)
    ]


def build_agent() -> Agent:
    """Returns an `Agent` that delegates to a `researcher` subagent via `Agent.as_tool()`.

    The same `PersistentFakeModel` instance backs both the orchestrator and the
    researcher -- one responder, told apart by `system_instructions` -- so this stays
    runnable fully offline, no API key, exactly like the vanilla and deepagents versions.
    """
    model = PersistentFakeModel(_fake_responder)
    researcher = Agent(name="researcher", instructions=RESEARCHER_INSTRUCTIONS, model=model)
    return Agent(
        name="orchestrator",
        instructions=ORCHESTRATOR_INSTRUCTIONS,
        model=model,
        tools=[researcher.as_tool(tool_name="research", tool_description="Research one subtopic in isolation and reports findings back.")],
    )
