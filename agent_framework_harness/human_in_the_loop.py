"""`human_in_the_loop`, expressed in Microsoft Agent Framework instead of vanilla LangGraph.

Same shape as
[`patterns/human_in_the_loop`](https://github.com/jithinkk/agentic-design-patterns/tree/main/patterns/human_in_the_loop):
a tool with a real-world side effect (`send_message`) pauses for a human decision before
it runs; read-only tools are untouched. What differs is how much of the gate you build
yourself.

Vanilla LangGraph makes the gate a node you write: `route_after_agent` checks whether
any pending tool call is in `TOOLS_REQUIRING_APPROVAL`, a `request_approval` node calls
`interrupt(...)`, and `route_after_approval` sends approved calls onward or injects a
denial `ToolMessage`. Every branch is yours, and visible.

Agent Framework collapses that to `@tool(approval_mode="always_require")` plus
`ToolApprovalMiddleware()` on the agent. When the model calls that tool, the run stops
with a `function_approval_request` `Content` in the response instead of running it; you
build a `function_approval_response` via `request.to_function_approval_response(approved=...)`
and send it back as the next message to resume -- carried in an `AgentSession`, which
plays the same role LangGraph's checkpointer does (state that survives between the pause
and the resume), but keyed to the session object you pass rather than a `thread_id`.
"""

from __future__ import annotations

import ast
import operator
import re

from agent_framework import Agent, AgentSession, Content, Message, ToolApprovalMiddleware, tool

from agent_framework_harness._fake_chat_client import PersistentFakeChatClient

_SEND_MESSAGE_RE = re.compile(r"send (?:a )?message to (\w+)[:,]?\s+(.+)", re.IGNORECASE)

_SAFE_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _eval_node(node: ast.AST) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _SAFE_OPERATORS:
        return _SAFE_OPERATORS[type(node.op)](_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _SAFE_OPERATORS:
        return _SAFE_OPERATORS[type(node.op)](_eval_node(node.operand))
    raise ValueError(f"Unsupported expression: {ast.dump(node)}")


@tool
def calculator(expression: str) -> str:
    """Evaluate a basic arithmetic expression, e.g. '(3 + 4) * 2'.

    Deliberately duplicated from `shared/tools/basic.py` rather than imported -- see the
    `send_message` docstring below for why non-LangChain harnesses can't reuse it.
    """
    tree = ast.parse(expression, mode="eval")
    return str(_eval_node(tree.body))


@tool(approval_mode="always_require")
def send_message(recipient: str, body: str) -> str:
    """Send a message to someone.

    A stand-in for any side-effecting real-world action, gated behind approval --
    deliberately duplicated from `shared/tools/basic.py` rather than imported: that
    module's tools are LangChain `@tool`-decorated and not compatible with this
    framework's own `@tool` decorator, so each non-LangChain harness defines its own.
    """
    return f"Message sent to {recipient}: {body!r}"


def _fake_responder(messages):
    last = messages[-1]
    if last.role == "tool":
        for c in last.contents:
            if c.type == "function_result":
                output = str(c.result)
                if "rejected" in output.lower():
                    return [Content(type="text", text="Understood — I won't do that.")]
                return [Content(type="text", text=f"Done: {output}")]

    question = next((c.text for m in reversed(messages) if m.role == "user" for c in m.contents if c.text), "")

    send_match = _SEND_MESSAGE_RE.search(question)
    if send_match:
        recipient, body = send_match.group(1), send_match.group(2)
        return [Content(type="function_call", call_id="call_1", name="send_message", arguments={"recipient": recipient, "body": body})]

    expr_match = re.search(r"[-+*/().\d\s]{3,}", question)
    if expr_match and any(op in expr_match.group() for op in "+-*/") and any(c.isdigit() for c in expr_match.group()):
        return [
            Content(type="function_call", call_id="call_1", name="calculator", arguments={"expression": expr_match.group().strip()})
        ]

    return [Content(type="text", text=f"[fake-client] No side-effecting action needed for: {question}")]


def build_agent() -> Agent:
    """Returns an `Agent` with `send_message` gated behind approval.

    Callers must pass an `AgentSession` to `agent.run(..., session=...)` -- the
    middleware raises if one isn't supplied, since approval state lives there, not on
    the agent itself. `run.py`'s `run_human_in_the_loop` creates one per call, playing
    the same role deepagents' `checkpointer` argument does.
    """
    return Agent(
        PersistentFakeChatClient(_fake_responder),
        "You are a helpful assistant. Use a tool when it would help; sending a message "
        "is a real action with consequences, so only do it when asked.",
        tools=[calculator, send_message],
        middleware=[ToolApprovalMiddleware()],
    )
