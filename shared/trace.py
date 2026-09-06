"""One trace vocabulary, shared by every harness.

The point of this repo is an apples-to-apples read: same two patterns,
five runtimes underneath. That only works if the five runs *report*
themselves the same way. Each `*_harness/run.py` converts its own result
shape into one of the dataclasses below (a `describe_*` function); the
renderers here turn those into an identical block layout, so two harnesses'
output diffs cleanly and the framework difference is what stands out.

The vocabulary deliberately matches the vanilla repo's narrated traces
(`agentic-design-patterns`, `run.py::render`): "fan-out", "subtasks
(runtime)", "gate", "PAUSED", "resume". Reading a harness trace next to
its vanilla equivalent should feel like the same story told twice.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

RULE = "─" * 64

_FINDINGS_RE = re.compile(r"Findings on (.+?):")


def subtasks_from_report(report_text: str) -> list[str]:
    """Recover the runtime-decided subtask list from a synthesized report.

    Every harness's `orchestrator_workers` fake worker emits a line that
    starts `Findings on <subtopic>:`, so the synthesized report carries the
    list the orchestrator actually fanned out to -- without this module
    needing to know any framework's message types.
    """
    return _FINDINGS_RE.findall(report_text or "")


def truncate(text: str, limit: int = 100) -> str:
    flat = " ".join((text or "").split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def _block(label: str, body: str) -> str:
    return f"\n{label}:\n{(body or '').rstrip()}"


@dataclass
class OrchestratorTrace:
    """How one harness ran `orchestrator_workers` for a request."""

    harness: str
    fanout_mechanism: str  # one line: the framework primitive that owns the fan-out
    subtasks: list[str]  # the runtime-decided list, in dispatch order
    isolation: str  # one line: how each subtask's context is kept separate
    final_report: str


@dataclass
class HitlTrace:
    """How one harness ran `human_in_the_loop` for a gated request."""

    harness: str
    gate_mechanism: str  # one line: the framework primitive that owns the gate
    gated_tool: str
    gated_args: dict
    interrupted: bool
    approved: bool
    resume_mechanism: str  # one line: how the decision gets back in
    final_text: str
    durable: bool = False  # is the paused state survive-a-restart durable?


def header(harness: str, pattern: str) -> str:
    return f"{harness} · {pattern}\n{RULE}"


def render_orchestrator(t: OrchestratorTrace) -> str:
    args = ", ".join(t.subtasks) if t.subtasks else "(none recovered)"
    lines = [
        header(t.harness, "orchestrator-workers"),
        f"  fan-out owner      : {t.fanout_mechanism}",
        f"  subtasks (runtime) : {len(t.subtasks)} — {args}",
        f"  isolation          : {t.isolation}",
        f"  synthesis          : orchestrator merges the {len(t.subtasks)} returned reports",
        _block("final report", t.final_report),
    ]
    return "\n".join(lines)


def run_demo(argv: list[str], default_task: str, *, describe_ow, describe_hitl) -> None:
    """Shared `__main__` body for every `*_harness/run.py`.

    `describe_ow(task) -> OrchestratorTrace` and `describe_hitl() -> HitlTrace`
    run their pattern and adapt the framework's result shape. `--otel`
    anywhere in argv additionally emits the OpenTelemetry span tree.
    """
    task = " ".join(a for a in argv if not a.startswith("-")) or default_task
    if "--otel" in argv:
        from shared.obs import enable_console_otel

        enable_console_otel()

    print(render_orchestrator(describe_ow(task)))
    print()
    print(render_hitl(describe_hitl()))


def render_hitl(t: HitlTrace) -> str:
    call = f"{t.gated_tool}(" + ", ".join(f"{k}={v!r}" for k, v in (t.gated_args or {}).items()) + ")"
    if not t.interrupted:
        decision = "gate never fired — no side-effecting tool was called"
    else:
        verdict = "APPROVED" if t.approved else "DENIED"
        outcome = "tool ran" if t.approved else "tool blocked; denial fed back to the agent"
        decision = f"{verdict} → {outcome}"
    lines = [
        header(t.harness, "human-in-the-loop"),
        f"  gate owner   : {t.gate_mechanism}",
        f"  gated tool   : {call}",
        f"  gate fired   : {'yes → run PAUSED before the tool ran' if t.interrupted else 'no'}",
        f"  decision     : {decision}",
        f"  resume       : {t.resume_mechanism}",
        f"  paused state : {'durable (survives a process restart)' if t.durable else 'in-memory'}",
        _block("final text", t.final_text),
    ]
    return "\n".join(lines)
