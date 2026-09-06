"""`human_in_the_loop`, expressed in the Strands Agents SDK instead of vanilla LangGraph.

Same shape as
[`patterns/human_in_the_loop`](https://github.com/jithinkk/agentic-design-patterns/tree/main/patterns/human_in_the_loop):
a tool with a real-world side effect (`send_message`) pauses for a human decision before
it runs; read-only tools are untouched. What differs is how much of the gate you build
yourself.

Vanilla LangGraph makes the gate a node you write: `route_after_agent` checks whether
any pending tool call is in `TOOLS_REQUIRING_APPROVAL`, a `request_approval` node calls
`interrupt(...)`, and `route_after_approval` sends approved calls onward or injects a
denial `ToolMessage`. Every branch is yours, and visible.

Strands collapses that to one intervention: `HumanInTheLoop(allowed_tools=[...])`. Every
tool NOT in `allowed_tools` pauses for approval by default -- the inverse of deepagents'
`interrupt_on={tool: True}` allowlist, an explicit denylist-by-default instead. The
mechanism is different too: rather than returning control to the caller (an
`interrupt()`/resume pair, or an `interruptions` list to resolve later),
`HumanInTheLoop`'s `ask` callback is invoked *inline*, synchronously, from inside the
same `agent.invoke_async()` call -- there is no separate resume step here, because the
decision is made by a function you supply up front rather than by a value the caller
sends back in a second call.
"""

from __future__ import annotations

import ast
import operator
import re

from strands import Agent, tool
from strands.vended_interventions.hitl.hitl import HumanInTheLoop

from strands_harness._fake_model import PersistentFakeModel

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

    A stand-in for any side-effecting real-world action. Not allow-listed in
    `build_agent()`'s `HumanInTheLoop`, so it's the one that pauses for approval --
    deliberately duplicated from `shared/tools/basic.py` rather than imported: that
    module's tools are LangChain `@tool`-decorated and not compatible with this SDK's
    own `@tool` decorator, so each non-LangChain harness defines its own.
    """
    return f"Message sent to {recipient}: {body!r}"


def _fake_responder(messages):
    last = messages[-1]
    if last["role"] == "user":
        for content in last["content"]:
            if "toolResult" in content:
                result = content["toolResult"]
                text = result["content"][0].get("text", "")
                if result["status"] == "error":
                    return [{"text": "Understood — I won't do that."}]
                return [{"text": f"Done: {text}"}]

    question = next((c["text"] for m in reversed(messages) if m["role"] == "user" for c in m["content"] if "text" in c), "")

    send_match = _SEND_MESSAGE_RE.search(question)
    if send_match:
        recipient, body = send_match.group(1), send_match.group(2)
        return [{"toolUse": {"toolUseId": "call_1", "name": "send_message", "input": {"recipient": recipient, "body": body}}}]

    expr_match = re.search(r"[-+*/().\d\s]{3,}", question)
    if expr_match and any(op in expr_match.group() for op in "+-*/") and any(c.isdigit() for c in expr_match.group()):
        return [{"toolUse": {"toolUseId": "call_1", "name": "calculator", "input": {"expression": expr_match.group().strip()}}}]

    return [{"text": f"[fake-model] No side-effecting action needed for: {question}"}]


def build_agent(*, approve: bool = True) -> Agent:
    """Returns an `Agent` with `send_message` gated behind approval.

    `approve` scripts the `ask` callback's answer up front, standing in for the human
    who'd otherwise type "yes"/"no" -- `HumanInTheLoop` calls it inline, so there's no
    separate resume step for `run.py` to drive the way the other harnesses need.
    """

    async def scripted_ask(prompt: str) -> str:
        return "yes" if approve else "no"

    return Agent(
        model=PersistentFakeModel(_fake_responder),
        tools=[calculator, send_message],
        interventions=[HumanInTheLoop(allowed_tools=["calculator"], ask=scripted_ask)],
    )
