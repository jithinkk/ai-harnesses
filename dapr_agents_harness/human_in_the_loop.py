"""`human_in_the_loop`, expressed in Dapr Agents instead of vanilla LangGraph.

Same shape as
[`patterns/human_in_the_loop`](https://github.com/jithinkk/agentic-design-patterns/tree/main/patterns/human_in_the_loop):
a tool with a real-world side effect (`send_message`) pauses for a human decision before
it runs; read-only tools are untouched. What differs is how much of the gate you build
yourself -- and, here, what actually persists the pause.

Vanilla LangGraph makes the gate a node you write: `route_after_agent` checks whether
any pending tool call is in `TOOLS_REQUIRING_APPROVAL`, a `request_approval` node calls
`interrupt(...)`, and `route_after_approval` sends approved calls onward or injects a
denial `ToolMessage`. Every branch is yours, and visible.

Dapr Agents gates via a `before_tool_call` hook that returns `RequireApproval(...)` --
the gate is the hook itself; nothing else is a gate unless a hook says so. Underneath,
the workflow calls `ctx.wait_for_external_event(...)` and genuinely suspends -- backed by
Dapr's durable state store, not an in-memory checkpointer, so the pause survives a
process restart the way LangGraph's `interrupt()` doesn't on its own. A human (or, here,
this harness) resolves it out-of-band by calling `agent.raise_approval_event(instance_id,
approval_request_id, approved=...)` -- no pub/sub or HTTP endpoint required for a
same-process caller, though both are how a real deployment would usually deliver it.
"""

from __future__ import annotations

import ast
import json
import operator
import re

from dapr_agents import DurableAgent, Hooks, Proceed, RequireApproval, tool
from dapr_agents.types.message import AssistantMessage, ToolCall

from dapr_agents_harness._fake_llm_client import PersistentFakeChatClient

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


@tool
def send_message(recipient: str, body: str) -> str:
    """Send a message to someone.

    A stand-in for any side-effecting real-world action. Gated by `build_agent()`'s
    `before_tool_call` hook, not by a decorator argument here -- deliberately duplicated
    from `shared/tools/basic.py` rather than imported: that module's tools are
    LangChain `@tool`-decorated and not compatible with this framework's own `@tool`
    decorator, so each non-LangChain harness defines its own.
    """
    return f"Message sent to {recipient}: {body!r}"


def _require_approval_for_send_message(ctx):
    """`before_tool_call` hook: the gate itself. No hook, no approval, ever."""
    if ctx.step_name == "send_message":
        return RequireApproval(reason="send_message is a real action with consequences.")
    return Proceed()


def _fake_responder(messages) -> AssistantMessage:
    last = messages[-1] if messages else {}
    if isinstance(last, dict) and last.get("role") == "tool":
        content = last.get("content", "")
        if "not executed" in content.lower() or "not granted" in content.lower():
            return AssistantMessage(text="Understood — I won't do that.")
        return AssistantMessage(text=f"Done: {content}")

    question = next((m.get("content", "") for m in reversed(messages) if isinstance(m, dict) and m.get("role") == "user"), "")

    send_match = _SEND_MESSAGE_RE.search(question)
    if send_match:
        recipient, body = send_match.group(1), send_match.group(2)
        return AssistantMessage(
            content=None,
            tool_calls=[ToolCall(id="call_1", type="function", function={"name": "send_message", "arguments": json.dumps({"recipient": recipient, "body": body})})],
        )

    expr_match = re.search(r"[-+*/().\d\s]{3,}", question)
    if expr_match and any(op in expr_match.group() for op in "+-*/") and any(c.isdigit() for c in expr_match.group()):
        return AssistantMessage(
            content=None,
            tool_calls=[ToolCall(id="call_1", type="function", function={"name": "calculator", "arguments": json.dumps({"expression": expr_match.group().strip()})})],
        )

    return AssistantMessage(text=f"[fake-model] No side-effecting action needed for: {question}")


def build_agent() -> DurableAgent:
    """Returns a `DurableAgent` with `send_message` gated behind approval.

    The hook is what makes `AgentApprovalConfig` (delivery plumbing) relevant at all --
    a `DurableAgent` with no `before_tool_call` hook never pauses for anything, no
    matter how `execution.approval` is configured.
    """
    return DurableAgent(
        name="assistant",
        role="assistant",
        instructions=[
            "Use a tool when it would help.",
            "Sending a message is a real action with consequences, so only do it when asked.",
        ],
        llm=PersistentFakeChatClient(_fake_responder),
        tools=[calculator, send_message],
        hooks=Hooks(before_tool_call=[_require_approval_for_send_message]),
    )
