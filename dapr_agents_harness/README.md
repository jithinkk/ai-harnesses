# The patterns under Dapr Agents

[Dapr Agents](https://github.com/dapr/dapr-agents) builds LLM-powered agents on top of
[Dapr](https://dapr.io)'s actor and durable-workflow runtime — every agent interaction
with the model and its tools is persisted to a durable state store, so an agent survives
a process restart mid-task. Unlike every other harness in this repo, it needs a real Dapr
sidecar process to run at all, not just a Python environment — see "The one accepted
exception" below before running this one locally.

Two patterns are implemented here, chosen because Dapr Agents expresses them natively.
The rest are documented below as non-fits — including a real, first-class Dapr Agents
capability this harness deliberately doesn't use.

| File | Vanilla equivalent | What Dapr Agents supplies |
|---|---|---|
| `orchestrator_workers.py` | [`patterns/orchestrator_workers`](https://github.com/jithinkk/agentic-design-patterns/tree/main/patterns/orchestrator_workers) | a `research` tool called once per subtopic, each execution a real, checkpointed workflow activity |
| `human_in_the_loop.py` | [`patterns/human_in_the_loop`](https://github.com/jithinkk/agentic-design-patterns/tree/main/patterns/human_in_the_loop) | a `before_tool_call` hook returning `RequireApproval(...)`, backed by `ctx.wait_for_external_event(...)` |

## The one accepted exception: this harness needs a real Dapr sidecar

Every other harness in this repo — deepagents, the OpenAI Agents SDK, Microsoft Agent
Framework, Strands — runs via a plain `uv sync` + `uv run pytest`, no extra process, no
extra infrastructure. Dapr Agents' actual differentiator is durable, sidecar-backed
workflow state, and there's no way to exercise that honestly without a real sidecar: this
repo's own bar for adding a harness says *"a harness that can only talk to a live
endpoint belongs in docs, not here"* — a sidecar dependency is the infrastructure
equivalent of that, and it would have been just as easy to scope this harness down to a
non-durable, non-sidecar surface to avoid it. That was a real option, considered and
rejected in favor of exercising the real feature rather than a version that doesn't
demonstrate what Dapr Agents is actually for.

Run it locally:

```bash
# Install the Dapr CLI (see https://docs.dapr.io/getting-started/install-dapr-cli/),
# then initialize the local runtime once:
dapr init --slim  # no Docker required; use --runtime-version if the version lookup
                  # is blocked, e.g. --runtime-version 1.15.4

uv sync --group dapr-agents
dapr run --app-id dapr-agents-harness -- uv run python -m dapr_agents_harness.run
dapr run --app-id dapr-agents-harness-test --resources-path dapr_agents_harness/components \
  -- uv run pytest dapr_agents_harness -v
```

`dapr_agents_harness/components/statestore.yaml` configures an in-memory, actor-capable
state store — no Redis, Postgres, or Docker needed beyond the Dapr CLI and runtime
themselves.

## What you stop writing

**The approval gate.** Vanilla spreads it across three functions —
`route_after_agent` checks pending calls against `TOOLS_REQUIRING_APPROVAL`,
`request_approval` calls `interrupt(...)`, and `route_after_approval` either proceeds or
injects a denial `ToolMessage`. Dapr Agents collapses it to one `before_tool_call` hook
returning `RequireApproval(...)` — everything else (suspending the workflow, persisting
the pending request, resuming on `raise_approval_event`) is the framework's.

## What you give up, concretely

- **The pause is a real suspended workflow instance, backed by durable state — not an
  in-memory checkpointer.** `run_human_in_the_loop` polls `agent.list_pending_approvals()`
  and calls `agent.raise_approval_event(instance_id, approval_request_id, approved=...)`
  directly in-process; a real deployment would instead deliver the pending request over
  pub/sub or poll `GET /hitl/approvals` in `serve()` mode, and resolve it the same way
  from a completely separate process — the workflow instance doesn't care which.
- **Dapr Agents' real multi-agent primitive, `call_agent`/`trigger_agent`, is not what
  this harness uses for `orchestrator_workers`.** That mechanism calls another
  `DurableAgent`'s workflow as a *durable child workflow across Dapr app/service
  boundaries* — genuinely distributed, matching Dapr's actor-model philosophy, and the
  framework's own idiomatic answer to "how do multiple agents coordinate." This harness
  uses a single agent with a `research` tool instead (the same Agents-as-Tools idiom
  every other harness in this repo uses for this pattern), because standing up a second
  app/service just to demonstrate one pattern would be a materially heavier kind of
  infrastructure than the sidecar exception already accepted above — a deliberate scope
  limitation, not evidence `call_agent` doesn't work. What's still real here: the
  `research` tool executes as genuine, durable, checkpointed workflow activities — the
  two calls in the fan-out test actually run concurrently and can complete in either
  order (verified against the real sidecar, not assumed).
- **A best-effort conversation-summarization call happens on a schedule this harness
  doesn't control.** Dapr Agents periodically asks the LLM for a structured
  `ConversationSummary` for long-term memory. This fake model answers it with a canned
  placeholder rather than routing it through the same scripted `responder` the two
  patterns use — neither demo depends on what the summary says, only that answering it
  doesn't crash the run.

## Patterns that don't fit, and why

Verified against `dapr-agents` 1.0.6 rather than assumed:

- **`prompt_chaining`** — a fixed sequence of model calls with a *programmatic* gate
  between them. `DurableAgent` is an agent loop: the model decides what happens next,
  turn by turn, same tension every framework in this repo runs into for this pattern.
- **`parallelization`** — needs a branch count fixed in code at agent-build time. The
  `research` tool's call count is decided by the model at runtime from the task text,
  which is `orchestrator_workers`' shape, not this one.
- **`routing`** — a single classification into a fixed branch set. Nothing here
  guarantees exactly one path is chosen the way a conditional edge deterministically does.
- **`evaluator_optimizer`** — a generate⇄evaluate cycle with a code-enforced iteration
  cap. `AgentExecutionConfig.max_iterations` bounds total turns, not rounds of refinement
  against explicit pass/fail criteria.
- **`react_agent`** — a tautology, not a non-fit: a plain `DurableAgent` with tools
  already *is* this loop. Reimplementing it here would show nothing the two above don't.

## Test it

```bash
dapr run --app-id dapr-agents-harness-test --resources-path dapr_agents_harness/components \
  -- uv run pytest dapr_agents_harness -v
```
