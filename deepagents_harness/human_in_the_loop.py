"""`human_in_the_loop`, expressed in deepagents instead of vanilla LangGraph.

Same shape as
[`patterns/human_in_the_loop`](https://github.com/jithinkk/agentic-design-patterns/tree/main/patterns/human_in_the_loop):
a tool with a real-world side effect (`send_message`) pauses for a human
decision before it runs; read-only tools are untouched. What differs is how
much of the gate you build yourself.

Vanilla LangGraph makes the gate a node you write: `route_after_agent`
checks whether any pending tool call is in `TOOLS_REQUIRING_APPROVAL`, a
`request_approval` node calls `interrupt(...)`, and `route_after_approval`
sends approved calls onward or injects a denial `ToolMessage`. Every branch
is yours, and visible.

deepagents collapses that to one argument: `interrupt_on={"send_message":
True}`. The gate, the pause, and the denial message are all supplied.

Two concrete differences worth knowing before porting between them:

- **The resume payload is richer, and shaped differently.** Vanilla resumes
  with a bare boolean, `Command(resume=True)`. deepagents expects
  `Command(resume={"decisions": [{"type": "approve"}]})`, and the interrupt
  advertises four decisions, not two: `approve`, `edit`, `reject`,
  `respond`. `edit` in particular has no equivalent in the hand-built
  version -- a reviewer can rewrite the tool's arguments before it runs.
- **The interrupt value is a structured envelope**, `{"action_requests":
  [...], "review_configs": [...]}`, rather than the payload this repo's own
  node chooses to pass to `interrupt(...)`.

Both still require a checkpointer, for the same reason: `interrupt()` pauses
mid-graph, and resuming is a separate `invoke()` call that has to find the
paused state again.
"""

from __future__ import annotations

import re

from deepagents import create_deep_agent
from langchain_core.messages import AIMessage, BaseMessage
from langgraph.checkpoint.memory import MemorySaver

from shared.llm.factory import get_chat_model
from shared.tools.basic import HITL_TOOLS

SYSTEM_PROMPT = (
    "You are a helpful assistant. Use a tool when it would help; sending a "
    "message is a real action with consequences, so only do it when asked."
)

# Only the side-effecting tool is gated. Read-only tools (calculator,
# search_docs, word_count) still run without interruption -- gating
# everything would cost the agent its autonomy for no safety gain.
TOOLS_REQUIRING_APPROVAL = {"send_message"}

_SEND_MESSAGE_RE = re.compile(r"send (?:a )?message to (\w+)[:,]?\s+(.+)", re.IGNORECASE)


def _fake_responder(messages: list[BaseMessage]) -> AIMessage:
    last = messages[-1]

    if last.type == "tool":
        if "rejected" in last.content.lower():
            return AIMessage(content="Understood — I won't do that.")
        return AIMessage(content=f"Done: {last.content}")

    question = next((m.content for m in reversed(messages) if m.type == "human"), "")

    send_match = _SEND_MESSAGE_RE.search(question)
    if send_match:
        recipient, body = send_match.group(1), send_match.group(2)
        return AIMessage(
            content="",
            tool_calls=[
                {"name": "send_message", "args": {"recipient": recipient, "body": body}, "id": "call_1"}
            ],
        )

    expr_match = re.search(r"[-+*/().\d\s]{3,}", question)
    if expr_match and any(op in expr_match.group() for op in "+-*/") and any(c.isdigit() for c in expr_match.group()):
        return AIMessage(
            content="",
            tool_calls=[{"name": "calculator", "args": {"expression": expr_match.group().strip()}, "id": "call_1"}],
        )

    return AIMessage(content=f"[fake-llm] No side-effecting action needed for: {question}")


def build_agent(checkpointer=None):
    """Returns a compiled deepagents graph with an approval gate.

    A checkpointer is required, not optional: `interrupt()` suspends the run
    and the resume arrives as a separate `invoke()` call, so the paused state
    has to persist between the two. `MemorySaver` is fine for a demo; a
    durable saver is what production needs.
    """
    return create_deep_agent(
        model=get_chat_model(responder=_fake_responder),
        tools=HITL_TOOLS,
        system_prompt=SYSTEM_PROMPT,
        interrupt_on={name: True for name in TOOLS_REQUIRING_APPROVAL},
        checkpointer=checkpointer or MemorySaver(),
    )
