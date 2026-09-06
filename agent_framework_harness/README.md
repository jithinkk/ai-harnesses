# The patterns under Microsoft Agent Framework

[Microsoft Agent Framework](https://github.com/microsoft/agent-framework) is Microsoft's
unified agent framework — the successor line to AutoGen and Semantic Kernel, with its own
runtime, its own model-client interface, and a distinct set of multi-agent
**orchestrations** (sequential, concurrent, group-chat, handoff, and Magentic) built on
top of its own `Workflow` executor/edge graph.

Two patterns are implemented here, chosen because the framework expresses them natively.
The rest are documented below as non-fits.

| File | Vanilla equivalent | What the framework supplies |
|---|---|---|
| `orchestrator_workers.py` | [`patterns/orchestrator_workers`](https://github.com/jithinkk/agentic-design-patterns/tree/main/patterns/orchestrator_workers) | **Magentic** orchestration — a manager decides, round by round, who acts next |
| `human_in_the_loop.py` | [`patterns/human_in_the_loop`](https://github.com/jithinkk/agentic-design-patterns/tree/main/patterns/human_in_the_loop) | `@tool(approval_mode="always_require")` + `ToolApprovalMiddleware` — the whole approval gate as two lines |

## What you stop writing

**Fan-out.** Vanilla LangGraph makes it explicit: `continue_to_workers` returns one
`Send("worker", ...)` per subtask, a `worker` node handles each, and an `operator.add`
reducer accumulates results before `synthesizer` runs. Magentic hands you a *manager*
abstraction instead — implement `create_progress_ledger()` to decide who speaks next each
round, and the framework's `MagenticOrchestrator` drives the loop, dispatches to the
chosen participant, and collects results into a shared `chat_history`.

**The approval gate.** Vanilla spreads it across three functions —
`route_after_agent` checks pending calls against `TOOLS_REQUIRING_APPROVAL`,
`request_approval` calls `interrupt(...)`, and `route_after_approval` either proceeds or
injects a denial `ToolMessage`. Agent Framework collapses it to a tool decorator argument
plus one middleware class.

## What you give up, concretely

- **Magentic's manager is normally an LLM call, not a deterministic function.** This
  harness's `ScriptedMagenticManager` implements the framework's own extension point
  (`plan`/`create_progress_ledger`/`replan`/`prepare_final_answer`) with fixed logic
  instead of `StandardMagenticManager`'s live model-driven planning — that's the
  trade this harness makes to stay offline. In production, `create_progress_ledger`
  is where the framework earns its name: it re-evaluates the whole task, participant
  roster, and history every round, an LLM call this harness deliberately replaces.
- **`FunctionInvocationLayer` is required, not automatic.** A `BaseChatClient` that
  doesn't mix it in silently gets no tool-calling loop at all — verified directly:
  omitting it produces an empty final response and only a logged warning, not an error.
- **Approval state lives in a session object you must remember to pass.**
  `ToolApprovalMiddleware` raises if `agent.run(..., session=...)` is called without an
  `AgentSession` — there's no default, unlike deepagents' optional
  `checkpointer=None` that falls back to `MemorySaver()`.

## Patterns that don't fit, and why

Verified against `agent-framework` 1.17.0 rather than assumed:

- **`prompt_chaining`** — a fixed sequence of model calls with a *programmatic* gate
  between them. Even Agent Framework's `SequentialBuilder` orchestration runs a fixed
  list of *agents* in order, not a mix of model calls and arbitrary Python conditionals
  between them — the gate would still have to live outside the orchestration.
- **`parallelization`** — needs a branch count fixed in code at build time. Agent
  Framework's `Workflow` fan-out/fan-in edges (`FanOutEdgeGroup`/`FanInEdgeGroup`) are
  the actual match for this one, not `ConcurrentBuilder`/Magentic — precisely the
  fixed-vs-dynamic distinction that put Magentic under `orchestrator_workers` instead.
- **`routing`** — a single classification into a fixed branch set. The framework's own
  `handoff` orchestration or `SwitchCaseEdgeGroup` can approximate it, but nothing
  guarantees exactly one route is chosen the way a conditional edge deterministically does.
- **`evaluator_optimizer`** — a generate⇄evaluate cycle with a code-enforced iteration
  cap. `max_round_count`/`max_stall_count` bound total rounds, not refinement against
  explicit pass/fail criteria the way this pattern's `should_continue` check does.
- **`react_agent`** — a tautology, not a non-fit: a plain `Agent` with tools already *is*
  this loop. Reimplementing it here would show nothing the two above don't.

## Run it

```bash
uv sync --group agent-framework
uv run python -m agent_framework_harness.run
```

Runs fully offline against `agent_framework_harness/_fake_chat_client.py`'s
`PersistentFakeChatClient` — no API key, no network.

## Test it

```bash
uv run pytest agent_framework_harness -v
```
