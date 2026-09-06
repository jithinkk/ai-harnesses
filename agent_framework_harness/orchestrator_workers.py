"""`orchestrator_workers`, expressed in Microsoft Agent Framework instead of vanilla LangGraph.

Same shape as
[`patterns/orchestrator_workers`](https://github.com/jithinkk/agentic-design-patterns/tree/main/patterns/orchestrator_workers):
an orchestrator decides at runtime how many independent subtasks a request needs, each
runs in its own isolated context, and the results are combined. The difference is who
owns the fan-out.

Vanilla LangGraph makes it explicit: `continue_to_workers` returns one `Send("worker",
...)` per subtask, a `worker` node handles each, and an `operator.add` reducer
accumulates results before `synthesizer` runs. You write the fan-out, so you can see and
test every edge of it.

Agent Framework's **Magentic** orchestration is the closer analogue to a *dynamic*,
runtime-decided fan-out than its `Workflow` fan-out/fan-in edges (those need the branch
count fixed at graph-build time -- that's `parallelization`, not this pattern, by the
same distinction `deepagents_harness/orchestrator_workers.py` draws). A Magentic
*manager* looks at the task and an evolving progress ledger, each round deciding who
speaks next -- normally itself an LLM call, deliberately replaced here with a small
deterministic `MagenticManagerBase` subclass, so the whole thing still runs offline. The
manager interface (`plan`/`create_progress_ledger`/`replan`/`prepare_final_answer`) is
the framework's own extension point, not a workaround -- real deployments can swap in
`StandardMagenticManager` (backed by a real model) without changing anything else here.
"""

from __future__ import annotations

import re

from agent_framework import Agent, Content, Message
from agent_framework.orchestrations import (
    MagenticBuilder,
    MagenticContext,
    MagenticManagerBase,
    MagenticProgressLedger,
    MagenticProgressLedgerItem,
)

from agent_framework_harness._fake_chat_client import PersistentFakeChatClient

RESEARCHER_NAME = "researcher"

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


def _researcher_responder(messages: list[Message]) -> list[Content]:
    last_user = next((m for m in reversed(messages) if m.role == "user"), None)
    subtopic = last_user.contents[0].text if last_user and last_user.contents else "the topic"
    return [Content(type="text", text=f"Findings on {subtopic}: three relevant points worth including in the report.")]


class ScriptedMagenticManager(MagenticManagerBase):
    """Deterministic manager: one subtopic per round, no live model call.

    Topics are extracted from `magentic_context.task` itself on the first ledger check
    (not passed in at construction) -- the same runtime-decided-count contract
    `orchestrator_workers` requires, and it keeps `build_agent()` task-agnostic like
    every other harness's, rather than needing the task upfront to configure the manager.
    """

    def __init__(self) -> None:
        super().__init__()
        self._topics: list[str] | None = None
        self._index = 0

    async def plan(self, magentic_context: MagenticContext) -> Message:
        self._topics = _extract_topics(magentic_context.task)
        return Message(role="assistant", contents=[Content(type="text", text=f"Plan: research {self._topics}")])

    async def replan(self, magentic_context: MagenticContext) -> Message:
        return await self.plan(magentic_context)

    async def create_progress_ledger(self, magentic_context: MagenticContext) -> MagenticProgressLedger:
        if self._topics is None:
            self._topics = _extract_topics(magentic_context.task)

        done = self._index >= len(self._topics)
        next_topic = "" if done else self._topics[self._index]
        participant = "" if done else next(iter(magentic_context.participant_descriptions))
        if not done:
            self._index += 1

        return MagenticProgressLedger(
            is_request_satisfied=MagenticProgressLedgerItem(reason="", answer=done),
            is_in_loop=MagenticProgressLedgerItem(reason="", answer=False),
            is_progress_being_made=MagenticProgressLedgerItem(reason="", answer=True),
            next_speaker=MagenticProgressLedgerItem(reason="", answer=participant),
            instruction_or_question=MagenticProgressLedgerItem(reason="", answer=next_topic),
        )

    async def prepare_final_answer(self, magentic_context: MagenticContext) -> Message:
        findings = [
            m.text for m in magentic_context.chat_history if m.role == "assistant" and m.text and "Findings on" in m.text
        ]
        return Message(role="assistant", contents=[Content(type="text", text="# Final Report\n\n" + "\n\n".join(findings))])


def build_agent():
    """Returns a compiled Magentic `Workflow`.

    `MagenticBuilder(...).build()` returns a real `agent_framework.Workflow` -- the
    orchestration is a layer over the framework's own workflow executor/edge machinery,
    not a separate runtime, the same "layer on the real thing, not a replacement for it"
    relationship deepagents has with LangGraph.
    """
    researcher = Agent(
        PersistentFakeChatClient(_researcher_responder),
        name=RESEARCHER_NAME,
        description="Researches one subtopic in isolation and reports findings back.",
    )
    return MagenticBuilder(participants=[researcher], manager=ScriptedMagenticManager()).build()
