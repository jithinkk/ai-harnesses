"""Run one pattern across every *installed* harness and print the traces
under aligned headers -- the side-by-side this repo is built around.

    uv run python compare.py                       # both patterns, every harness
    uv run python compare.py orchestrator-workers  # just one pattern
    uv run python compare.py human-in-the-loop --otel

A base `uv sync` installs only `deepagents`; the other four harnesses live
behind conflicting optional groups (`uv sync --group strands`, etc.), so
whichever you have installed is what you get compared. A harness that
imports fine but needs external infra (Dapr's sidecar) is reported as a
skip with its error, not a crash.

Each harness's `run.py` supplies `describe_orchestrator_workers(task)` and
`describe_human_in_the_loop()`, which run the pattern and adapt the
framework's result into `shared/trace.py`'s common shape. This script only
lays them out.
"""

from __future__ import annotations

import importlib
import sys
import traceback

from shared.trace import RULE, render_hitl, render_orchestrator

# comparison.md's table order.
HARNESSES = ["deepagents", "openai_agents", "agent_framework", "strands", "dapr_agents"]

PATTERNS = {
    "orchestrator-workers": ("describe_orchestrator_workers", render_orchestrator, True),
    "human-in-the-loop": ("describe_human_in_the_loop", render_hitl, False),
}

DEFAULT_TASK = "Write a short product report covering pricing, onboarding, and support quality."


def _run_one(module, describe_name: str, renderer, needs_task: bool, task: str) -> str:
    describe = getattr(module, describe_name)
    trace = describe(task) if needs_task else describe()
    return renderer(trace)


def compare(pattern: str, *, task: str = DEFAULT_TASK, otel: bool = False) -> str:
    if pattern not in PATTERNS:
        raise SystemExit(f"unknown pattern {pattern!r}; choose from: {', '.join(PATTERNS)} (or 'all')")

    if otel:
        from shared.obs import enable_console_otel

        enable_console_otel()

    describe_name, renderer, needs_task = PATTERNS[pattern]
    out: list[str] = [f"### {pattern} — {sum_installed()} of {len(HARNESSES)} harness(es) installed", ""]

    for name in HARNESSES:
        try:
            module = importlib.import_module(f"{name}_harness.run")
        except ImportError as exc:
            out += [f"{name.replace('_', '-')} · {pattern}", RULE, f"  skipped — not installed ({exc})", ""]
            continue
        try:
            out += [_run_one(module, describe_name, renderer, needs_task, task), ""]
        except Exception:  # a harness that imports but can't run (e.g. Dapr sidecar down)
            tb = traceback.format_exc(limit=1).strip().splitlines()[-1]
            out += [f"{name.replace('_', '-')} · {pattern}", RULE, f"  skipped — installed but did not run ({tb})", ""]

    return "\n".join(out)


def sum_installed() -> int:
    n = 0
    for name in HARNESSES:
        try:
            importlib.import_module(f"{name}_harness.run")
            n += 1
        except ImportError:
            pass
    return n


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    otel = "--otel" in argv
    positional = [a for a in argv if not a.startswith("-")]
    pattern = positional[0] if positional else "all"

    targets = list(PATTERNS) if pattern == "all" else [pattern]
    for i, target in enumerate(targets):
        if i:
            print("\n" + "=" * 72 + "\n")
        print(compare(target, otel=otel))


if __name__ == "__main__":
    main()
