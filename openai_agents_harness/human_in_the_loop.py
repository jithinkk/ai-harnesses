"""`human_in_the_loop`, expressed in the OpenAI Agents SDK instead of vanilla LangGraph.

Same shape as
[`patterns/human_in_the_loop`](https://github.com/jithinkk/agentic-design-patterns/tree/main/patterns/human_in_the_loop):
a tool with a real-world side effect (`send_message`) pauses for a human decision before
it runs; read-only tools are untouched. What differs is how much of the gate you build
yourself.

Vanilla LangGraph makes the gate a node you write: `route_after_agent` checks whether
any pending tool call is in `TOOLS_REQUIRING_APPROVAL`, a `request_approval` node calls
`interrupt(...)`, and `route_after_approval` sends approved calls onward or injects a
denial `ToolMessage`. Every branch is yours, and visible.

The Agents SDK collapses that to one argument: `@function_tool(needs_approval=True)`.
When the model calls that tool, `Runner.run()` returns with `RunResult.interruptions`
populated (a list of `ToolApprovalItem`) instead of running it; you approve or reject via
`RunState.approve()`/`.reject()` on `result.to_state()`, then pass that state back into
`Runner.run()` to resume -- no separate checkpointer needed, unlike LangGraph's
`interrupt()`, since the whole pending state is carried in the returned `RunState` object
itself rather than looked up by a `thread_id`.
"""

from __future__ import annotations

import ast
import operator
import re

from agents import Agent, function_tool
from agents.testing.model import assistant_message, function_call

from openai_agents_harness._fake_model import PersistentFakeModel

# Only the side-effecting tool is gated. The read-only tool below still runs without
# interruption -- gating everything would cost the agent its autonomy for no safety gain.
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


@function_tool
def calculator(expression: str) -> str:
    """Evaluate a basic arithmetic expression, e.g. '(3 + 4) * 2'.

    Deliberately duplicated from `shared/tools/basic.py` rather than imported -- see the
    `send_message` docstring below for why non-LangChain harnesses can't reuse it.
    """
    tree = ast.parse(expression, mode="eval")
    return str(_eval_node(tree.body))


@function_tool(needs_approval=True)
def send_message(recipient: str, body: str) -> str:
    """Send a message to someone.

    A stand-in for any side-effecting real-world action, gated behind approval --
    deliberately duplicated from `shared/tools/basic.py` rather than imported: that
    module's tools are LangChain `@tool`-decorated and not compatible with this SDK's
    own `@function_tool` decorator, so each non-LangChain harness defines its own.
    """
    return f"Message sent to {recipient}: {body!r}"


def _fake_responder(system_instructions, input):
    last = input[-1] if input else None
    if isinstance(last, dict) and last.get("type") == "function_call_output":
        output = last["output"]
        if "rejected" in output.lower():
            return [assistant_message("Understood — I won't do that.")]
        return [assistant_message(f"Done: {output}")]

    question = next((i.get("content") for i in reversed(input) if i.get("role") == "user"), "")

    send_match = _SEND_MESSAGE_RE.search(question)
    if send_match:
        recipient, body = send_match.group(1), send_match.group(2)
        return [function_call("send_message", {"recipient": recipient, "body": body}, call_id="call_1")]

    expr_match = re.search(r"[-+*/().\d\s]{3,}", question)
    if expr_match and any(op in expr_match.group() for op in "+-*/") and any(c.isdigit() for c in expr_match.group()):
        return [function_call("calculator", {"expression": expr_match.group().strip()}, call_id="call_1")]

    return [assistant_message(f"[fake-model] No side-effecting action needed for: {question}")]


def build_agent() -> Agent:
    """Returns an `Agent` with `send_message` gated behind approval.

    No checkpointer to pass in, unlike deepagents' `build_agent(checkpointer=None)`: the
    SDK's resumable `RunState` already carries everything needed to continue a paused
    run, so there's nothing separate to persist between the pause and the resume here.
    """
    return Agent(
        name="assistant",
        instructions=(
            "You are a helpful assistant. Use a tool when it would help; sending a "
            "message is a real action with consequences, so only do it when asked."
        ),
        model=PersistentFakeModel(_fake_responder),
        tools=[calculator, send_message],
    )
