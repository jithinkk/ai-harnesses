"""A small, dependency-free toolset shared by the tool-using patterns.

Kept intentionally simple (arithmetic, an in-memory doc lookup, a word
counter) so the deepagents harness demos can be exercised end-to-end
without any external API.
"""

from __future__ import annotations

import ast
import math
import operator

from langchain_core.tools import tool

_MAX_EXPRESSION_LENGTH = 200
_MAX_POW_RESULT_BITS = 10_000  # ~3,000 decimal digits; computes instantly


def _safe_pow(base: float, exponent: float) -> float:
    """`operator.pow`, but rejects operands whose result would be absurdly large.

    Python integers are arbitrary precision, so an innocuous-looking
    expression like `99999999**99999999` computes a ~2.66-billion-bit
    number and can hang a process indefinitely with no error and no
    timeout. Reject anything whose result would exceed a few thousand
    bits *before* computing it, rather than after.

    This and `_MAX_EXPRESSION_LENGTH` below are this repo's only two real
    guardrails (both at the "tool execution" boundary); see
    docs/harnesses-and-loops.md ("Guardrails") for the other two
    boundaries (input, output) this repo doesn't guard at all.
    """
    if exponent != 0 and base not in (0, 1, -1):
        estimated_bits = abs(exponent) * math.log2(max(abs(base), 2))
        if estimated_bits > _MAX_POW_RESULT_BITS:
            raise ValueError(f"result too large ({estimated_bits:.0f} bits estimated)")
    return operator.pow(base, exponent)


_SAFE_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: _safe_pow,
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
    """Evaluate a basic arithmetic expression, e.g. '(3 + 4) * 2'."""
    if len(expression) > _MAX_EXPRESSION_LENGTH:
        return f"error: expression too long ({len(expression)} chars, max {_MAX_EXPRESSION_LENGTH})"
    try:
        tree = ast.parse(expression, mode="eval")
        return str(_eval_node(tree.body))
    except Exception as exc:
        return f"error: could not evaluate {expression!r} ({exc})"


_DOCS = {
    "langgraph": "LangGraph is a library for building stateful, multi-actor "
    "applications with LLMs, modeled as a graph of nodes and edges.",
    "react": "ReAct interleaves reasoning traces and actions: the model "
    "decides whether to call a tool or answer, observes the result, and repeats.",
    "orchestrator": "The orchestrator-workers pattern has a central LLM "
    "dynamically break a task into subtasks and delegate them to worker LLMs.",
    "evaluator": "The evaluator-optimizer pattern loops a generator against "
    "an evaluator that grades output and returns feedback until it passes.",
}


@tool
def search_docs(query: str) -> str:
    """Search a small built-in glossary of agentic-pattern terms."""
    query = query.lower()
    hits = [text for key, text in _DOCS.items() if key in query]
    if not hits:
        return "No matching entries found."
    return "\n".join(hits)


@tool
def word_count(text: str) -> str:
    """Count the words in a piece of text."""
    return str(len(text.split()))


@tool
def send_message(recipient: str, body: str) -> str:
    """Send a message to someone.

    A stand-in for any side-effecting real-world action (send an email,
    post to Slack, place an order): safe and offline here, but the kind of
    call a production system would gate behind human approval before it
    actually runs. Deliberately excluded from `ALL_TOOLS` -- only
    `human_in_the_loop` under `deepagents_harness` is wired up with the
    approval gate this needs.
    """
    return f"Message sent to {recipient}: {body!r}"


ALL_TOOLS = [calculator, search_docs, word_count]
HITL_TOOLS = [*ALL_TOOLS, send_message]
