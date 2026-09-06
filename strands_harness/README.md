# The patterns under the Strands Agents SDK

[Strands Agents SDK](https://github.com/strands-agents/sdk-python) is AWS's open-source,
code-first agent framework — model-driven loop, tools via a `@tool` decorator, and three
distinct multi-agent patterns (Graph, Swarm, Agents-as-Tools) that ship with the SDK
itself. Like the other harnesses here, it's its own runtime, not built on LangGraph.

Two patterns are implemented here, chosen because the SDK expresses them natively. The
rest are documented below as non-fits.

| File | Vanilla equivalent | What the SDK supplies |
|---|---|---|
| `orchestrator_workers.py` | [`patterns/orchestrator_workers`](https://github.com/jithinkk/agentic-design-patterns/tree/main/patterns/orchestrator_workers) | **Agents-as-Tools** — wrap a subagent call in a plain `@tool`, delegate to as many as one turn calls |
| `human_in_the_loop.py` | [`patterns/human_in_the_loop`](https://github.com/jithinkk/agentic-design-patterns/tree/main/patterns/human_in_the_loop) | `HumanInTheLoop(allowed_tools=[...])` — every non-allow-listed tool pauses for approval |

## What you stop writing

**Fan-out.** Vanilla LangGraph makes it explicit: `continue_to_workers` returns one
`Send("worker", ...)` per subtask, a `worker` node handles each, and an `operator.add`
reducer accumulates results before `synthesizer` runs. Here, `research` is a plain
`@tool` function that runs a fresh `Agent` internally; the orchestrator calls it once per
subtask in one turn, and each call's result comes back as a normal tool result.

**The approval gate.** Vanilla spreads it across three functions —
`route_after_agent` checks pending calls against `TOOLS_REQUIRING_APPROVAL`,
`request_approval` calls `interrupt(...)`, and `route_after_approval` either proceeds or
injects a denial `ToolMessage`. Strands collapses it to one intervention:
`HumanInTheLoop(allowed_tools=["calculator"])`.

## What you give up, concretely

- **The SDK actually ships three multi-agent patterns, and only one fits this pattern.**
  **Graph** is a *deterministic* directed graph with edges fixed at build time — that's
  `parallelization`'s shape, not `orchestrator_workers`'. **Swarm** is a peer-to-peer
  relay: agents hand the whole conversation to each other via an injected
  `handoff_to_agent` tool, and whichever agent's turn ends without a further handoff
  produces the answer — a genuinely different collaboration model (open-ended team
  hand-offs, not "dispatch N, collect N, synthesize"), and its stateful turn-passing made
  it the least reliable of the three to script deterministically for this demo.
  Agents-as-Tools is the one that actually matches.
- **The approval default is inverted, and the mechanism is inline, not resumable.**
  Deepagents' `interrupt_on={tool: True}` is an allowlist of what to gate; `HumanInTheLoop`'s
  `allowed_tools` is an allowlist of what to *skip* — everything else pauses by default.
  And there's no separate resume call here: `ask` is invoked synchronously from inside the
  same `invoke_async()`, so the decision has to be scripted into the agent up front
  (`build_agent(approve=...)`), not supplied after the fact the way `RunState.approve()`/
  deepagents' `Command(resume=...)` are.
- **You get a filesystem and shell tools whether you asked for one or not**, if you use
  the framework's `Agent()` with no `tools=` argument at all — Strands binds a default
  toolset in that case. This harness always passes an explicit `tools=[...]` list, so it
  isn't exposed to that, but it's a real default worth knowing before dropping the
  argument in your own code.

## Patterns that don't fit, and why

Verified against `strands-agents` 1.54.0 rather than assumed:

- **`prompt_chaining`** — a fixed sequence of model calls with a *programmatic* gate
  between them. Strands' Graph pattern is deterministic but connects *agents*, not
  arbitrary Python conditionals between model calls — the gate would still have to live
  outside it.
- **`parallelization`** — needs a branch count fixed in code at build time. That's
  Graph's shape, not Agents-as-Tools' (model-decided count) or Swarm's (relay, not
  fan-out) — Graph isn't implemented here because this repo only implements the two
  patterns each framework expresses *most* natively, and Agents-as-Tools already covers
  `orchestrator_workers`.
- **`routing`** — a single classification into a fixed branch set. Nothing in Strands'
  multi-agent toolkit guarantees exactly one path is chosen the way a conditional edge
  deterministically does; Swarm's handoffs can approximate it but are open-ended by design.
- **`evaluator_optimizer`** — a generate⇄evaluate cycle with a code-enforced iteration
  cap. Nothing in the SDK bounds *rounds of refinement against explicit pass/fail
  criteria* the way this pattern's `should_continue` check does.
- **`react_agent`** — a tautology, not a non-fit: a plain `Agent` with tools already *is*
  this loop. Reimplementing it here would show nothing the two above don't.

## Run it

```bash
uv sync --group strands
uv run python -m strands_harness.run
```

Runs fully offline against `strands_harness/_fake_model.py`'s `PersistentFakeModel` — no
API key, no network.

## Test it

```bash
uv run pytest strands_harness -v
```
