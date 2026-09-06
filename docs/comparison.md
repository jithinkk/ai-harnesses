# Framework Comparison

Every harness in this repo re-expresses the same two patterns —
`orchestrator_workers` and `human_in_the_loop` — so the comparison is
apples-to-apples: same task, five different runtimes' worth of machinery
underneath it. This page is the cross-cutting view; each harness's own
README goes deeper on its specific trade-offs and non-fits.

## Running it

The table below is also something you can *run*. `compare.py` executes one
pattern across every installed harness and prints the traces under aligned
headers, so the difference is a clean read rather than five separate
scrollbacks:

```bash
uv run python compare.py                       # both patterns, every installed harness
uv run python compare.py orchestrator-workers  # just one pattern
uv run python compare.py human-in-the-loop --otel
```

A base `uv sync` installs only `deepagents`; the other four sit behind
conflicting optional groups (`uv sync --group strands`, `--group
openai-agents`, …), so whichever you have is what gets compared, and the
rest render as labelled skip lines. Each `*_harness/run.py` still runs on
its own (`uv run python -m strands_harness.run`) and now prints the same
structured trace — the harness name, the fan-out owner, the runtime
subtask count, the gate mechanism, how resume works — so a single run
lines up against its vanilla equivalent in
[`agentic-design-patterns`](https://jithinkk.github.io/agentic-design-patterns/observability/).
`--otel` on either adds the OpenTelemetry span tree — see
[Observability](observability.md).

| Harness | Runtime substrate | Delegation mechanism (`orchestrator_workers`) | HITL mechanism (`human_in_the_loop`) | Offline fake |
|---|---|---|---|---|
| [deepagents](deepagents.md) | Built on LangGraph — returns a real `CompiledStateGraph` | Built-in `task` tool — model calls `task(subagent_type, description)`, subagent runs in a fresh context, returns one summary | `interrupt_on={tool: True}` — LangGraph's `interrupt()` + a checkpointer; pause and resume are separate `invoke()` calls | `BaseChatModel` — `shared/llm/fake.py`'s `FakeChatModel` drops in directly |
| [OpenAI Agents SDK](openai-agents.md) | Its own runtime (successor to Swarm) — no LangGraph | `Agent.as_tool()` — wraps a specialist agent as a callable tool; fans out to several in one turn, unlike a sequential handoff | `needs_approval` on a tool → `RunResult.interruptions` (`ToolApprovalItem`) → `RunState.approve()`/`.reject()` → resume | The SDK's `Model` interface, implemented directly |
| [Microsoft Agent Framework](agent-framework.md) | Its own `Workflow` executor/edge runtime — no LangGraph | **Magentic** orchestration — a manager decides who acts next each round via a progress ledger | A `before_tool_call`-style request/response mechanism — the workflow pauses via `RequestInfoExecutor` and resumes on an external response | `BaseChatClient` + `FunctionInvocationLayer` mixin (required, or the tool-calling loop silently never runs) |
| [Strands Agents SDK](strands.md) | Its own runtime — no LangGraph | **Agents-as-Tools** — a plain `@tool` function runs a fresh `Agent` internally; the SDK also ships Graph (build-time-fixed) and Swarm (peer-to-peer handoff relay), neither a fit here | `HumanInTheLoop(allowed_tools=[...])` — an inverted, allow-list default; the `ask` callback decides inline, no separate resume call | `Model` — `stream()` is an async generator of low-level streaming events, the most different interface of the three non-Dapr frameworks |
| [Dapr Agents](dapr-agents.md) | Dapr's actor + durable Workflow engine — the only harness needing a real sidecar | A single agent's tool called once per subtopic, as real checkpointed workflow activities (the framework's own cross-service `call_agent` primitive is out of scope here — see its README) | A `before_tool_call` hook returns `RequireApproval(...)`; the workflow suspends via `wait_for_external_event`, resumed by `raise_approval_event(...)` — durable, not in-memory | `ChatClientBase` — mock the LLM-client layer, per Dapr's own unit-test guidance, not the sidecar |

## What stays constant, what varies

Every harness's fake model follows the same shape regardless of the
framework's own interface: a single persistent `responder` callable that
inspects the growing message history and returns what the "model" should
say next — the same idiom `shared/llm/fake.py`'s `FakeChatModel` uses for
the vanilla patterns and deepagents. What varies is how much plumbing sits
between that responder and the framework: a plain return value
(deepagents, OpenAI Agents SDK, Microsoft Agent Framework, Dapr Agents) vs.
a hand-assembled low-level streaming-event sequence (Strands).

The five HITL mechanisms split cleanly into two families:

- **Resumable state, decided by the caller after the fact** — deepagents
  (`Command(resume=...)` + checkpointer), OpenAI Agents SDK (`RunState`),
  Microsoft Agent Framework (request/response), Dapr Agents
  (`raise_approval_event`, durable). All four pause, return control, and
  wait for a separate call to resume.
- **Decided inline, by a callback supplied up front** — Strands'
  `HumanInTheLoop(ask=...)`. There's no separate resume step because the
  decision function is already wired in before the run starts.

Only Dapr Agents' pause is backed by genuinely durable state — it would
survive the process restarting mid-approval; the other four hold the
paused state in memory (or a pluggable-but-not-exercised-here persistence
layer, in deepagents' case).
