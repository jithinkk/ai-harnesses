# The patterns under the OpenAI Agents SDK

[The OpenAI Agents SDK](https://github.com/openai/openai-agents-python) is OpenAI's own
production framework — four primitives (agents, tools, handoffs, guardrails) built on the
Responses API. Unlike deepagents, it isn't built *on* LangGraph — it's its own runtime,
with its own model interface, its own multi-agent mechanisms, and its own approval flow.

Two patterns are implemented here, chosen because the SDK expresses them natively. The
rest are documented below as non-fits.

| File | Vanilla equivalent | What the SDK supplies |
|---|---|---|
| `orchestrator_workers.py` | [`patterns/orchestrator_workers`](https://github.com/jithinkk/agentic-design-patterns/tree/main/patterns/orchestrator_workers) | `Agent.as_tool()` — wrap a specialist agent as a callable tool, delegate to as many as one turn calls |
| `human_in_the_loop.py` | [`patterns/human_in_the_loop`](https://github.com/jithinkk/agentic-design-patterns/tree/main/patterns/human_in_the_loop) | `@function_tool(needs_approval=True)` — the whole approval gate as one argument |

## What you stop writing

**Fan-out.** Vanilla LangGraph makes it explicit: `continue_to_workers` returns one
`Send("worker", ...)` per subtask, a `worker` node handles each, and an `operator.add`
reducer accumulates results before `synthesizer` runs. In the Agents SDK you wrap a
subagent with `Agent.as_tool()` and hand it to the orchestrator's `tools=[...]`; the
model delegates by calling that tool, once per subtask, and the SDK runs each call and
returns its output as a tool result the orchestrator reads.

**The approval gate.** Vanilla spreads it across three functions —
`route_after_agent` checks pending calls against `TOOLS_REQUIRING_APPROVAL`,
`request_approval` calls `interrupt(...)`, and `route_after_approval` either proceeds or
injects a denial `ToolMessage`. The SDK collapses all of it to
`@function_tool(needs_approval=True)`.

## What you give up, concretely

- **`as_tool()` is not a handoff, and the difference matters.** A *handoff* transfers the
  *entire conversation* to another agent, which then takes over completely — the
  orchestrator never sees its output. `as_tool()` calls the subagent with *generated
  input* and returns control to the caller — the orchestrator gets the result back as a
  tool output and keeps going. Only `as_tool()` fans out to several subagents in one
  turn; a handoff can only ever go to exactly one.
- **The resume mechanism carries its own state, not a `thread_id`.** Vanilla resumes with
  `Command(resume=True)` against a checkpointer keyed by `thread_id`. The SDK's
  `RunResult.to_state()` returns a `RunState` object that already contains everything
  needed to continue — no separate persistence layer to stand up, but also nothing to
  look up by ID if you want to resume from a different process than the one that paused.
- **The interrupt value is a `ToolApprovalItem`**, not a payload your own node chooses to
  pass to `interrupt(...)` — fixed fields (`tool_name`, `arguments`, `agent`), and
  `RunState.approve()`/`.reject()` are the only two decisions, unlike deepagents'
  four (`approve`, `edit`, `reject`, `respond`).

## Patterns that don't fit, and why

Verified against `openai-agents` 0.22.0 rather than assumed:

- **`prompt_chaining`** — a fixed sequence of model calls with a *programmatic* gate
  between them. The SDK is an agent loop: the model decides what happens next, turn by
  turn. There's no way to say "call A, then evaluate this Python condition, then call B"
  without the model itself making that call — the same tension every agent framework in
  this repo runs into for this pattern.
- **`parallelization`** — needs a branch count fixed in code at agent-build time.
  `as_tool()` delegation is model-decided at runtime and returns as tool outputs the
  model reads, not through a reducer you control. That's `orchestrator_workers` by
  construction, which is why it's implemented here and this one isn't.
- **`routing`** — a single classification into a fixed branch set. `handoff`s can
  approximate it (a triage agent hands off to exactly one specialist), but nothing
  guarantees the model hands off exactly once to exactly one target the way a
  conditional edge deterministically does.
- **`evaluator_optimizer`** — a generate⇄evaluate cycle with a code-enforced iteration
  cap. `max_turns` bounds total turns, not rounds of refinement against explicit
  pass/fail criteria.
- **`react_agent`** — a tautology, not a non-fit: the SDK's core loop *is* a ReAct-style
  tool loop. Reimplementing it here would show nothing the two above don't.

## Run it

```bash
uv sync --group openai-agents
uv run python -m openai_agents_harness.run
```

Runs fully offline against `openai_agents_harness/_fake_model.py`'s `PersistentFakeModel`
— no API key, no network. The SDK's `Model` interface is implemented directly (not routed
through a local Ollama-compatible endpoint or similar), the same offline guarantee every
other harness in this repo has.

## Test it

```bash
uv run pytest openai_agents_harness -v
```
