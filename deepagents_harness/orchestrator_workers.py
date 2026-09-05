"""`orchestrator_workers`, expressed in deepagents instead of vanilla LangGraph.

Same shape as
[`patterns/orchestrator_workers`](https://github.com/jithinkk/agentic-design-patterns/tree/main/patterns/orchestrator_workers):
an orchestrator decides at runtime how many independent subtasks a request
needs, each runs in its own isolated context, and the results are combined.
The difference is who owns the fan-out.

Vanilla LangGraph makes it explicit: `continue_to_workers` returns one
`Send("worker", ...)` per subtask, a `worker` node handles each, and an
`operator.add` reducer accumulates results before `synthesizer` runs. You
write the fan-out, so you can see and test every edge of it.

deepagents hands you that machinery as a built-in `task` tool. You declare
subagents up front; the model delegates by calling `task` with a
`subagent_type` and a `description`, and each invocation runs statelessly
in a fresh context window and returns a single report. The fan-out is the
framework's, not yours -- which is the whole trade being illustrated here.
"""

from __future__ import annotations

import re

from deepagents import create_deep_agent
from langchain_core.messages import AIMessage, BaseMessage

from shared.llm.factory import get_chat_model

# Marker in the researcher subagent's system prompt, so the one scripted
# responder can tell an orchestrator turn from a subagent turn. Same idiom
# the vanilla patterns use (see patterns/routing/nodes.py's "STAGE: X").
_RESEARCHER_MARKER = "STAGE: WORKER"

ORCHESTRATOR_PROMPT = (
    "You coordinate research. Break the request into independent subtopics "
    "and delegate each one to the `researcher` subagent with the `task` tool, "
    "then combine what comes back into one report."
)

RESEARCHER_PROMPT = f"{_RESEARCHER_MARKER}. Research the single subtopic you are given and report findings."

# Deliberately duplicated from patterns/orchestrator_workers/nodes.py rather
# than imported: the two implementations are meant to be readable side by
# side without one depending on the other's internals.
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


def _fake_responder(messages: list[BaseMessage]) -> AIMessage:
    system = messages[0].content if messages else ""

    # A researcher subagent turn: deepagents runs it with its own system
    # prompt in a fresh context, so the marker is how we recognise it.
    if _RESEARCHER_MARKER in system:
        subtopic = messages[-1].content
        return AIMessage(content=f"Findings on {subtopic}: three relevant points worth including in the report.")

    # An orchestrator turn. If results are already back, synthesise; otherwise
    # fan out with one `task` call per subtopic. Emitting several tool calls in
    # one message is how deepagents runs subagents concurrently -- the direct
    # analogue of returning several `Send`s from a conditional edge.
    delegated = any(getattr(m, "name", None) == "task" for m in messages)
    if delegated:
        reports = [m.content for m in messages if getattr(m, "name", None) == "task"]
        return AIMessage(content="# Final Report\n\n" + "\n\n".join(reports))

    first_human = next((m.content for m in messages if m.type == "human"), "")
    topics = _extract_topics(first_human)
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": "task",
                "args": {"description": topic, "subagent_type": "researcher"},
                "id": f"call_{i}",
            }
            for i, topic in enumerate(topics)
        ],
    )


def build_agent():
    """Returns a compiled deepagents graph.

    `create_deep_agent` returns a real LangGraph `CompiledStateGraph`, so
    `.invoke()`, `.stream()` and checkpointers behave exactly as they do for
    this repo's hand-built graphs -- deepagents is a layer on LangGraph, not
    a replacement for it.

    Passing a `BaseChatModel` instance (rather than a `"provider:model"`
    string) is what keeps this runnable offline: `model` is typed
    `str | BaseChatModel | None`, so the repo's `FakeChatModel` drops in.
    """
    return create_deep_agent(
        model=get_chat_model(responder=_fake_responder),
        system_prompt=ORCHESTRATOR_PROMPT,
        subagents=[
            {
                "name": "researcher",
                "description": "Researches one subtopic in isolation and reports findings back.",
                "system_prompt": RESEARCHER_PROMPT,
            }
        ],
    )
