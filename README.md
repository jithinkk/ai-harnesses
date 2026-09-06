# ai-harnesses

A DIY repo to explore various harnesses and to do a trade-off analysis.

The seven patterns in
[`agentic-design-patterns`](https://github.com/jithinkk/agentic-design-patterns)
are written in vanilla LangGraph, hand-built with no framework dependency.
This repo answers a different, narrower question — **should you hand-build a
pattern, or let a framework supply it?** — by re-expressing some of those
patterns through real agent-harness frameworks and comparing them side by
side with their vanilla equivalents.

For the conceptual background — the agent loop vs. the harness around it,
different harness archetypes and what should guide picking one, and what
production adds beyond the graphs (memory, guardrails, MCP tool
integration, evals) — see
[`docs/harnesses-and-loops.md`](docs/harnesses-and-loops.md).

## What's here

- [`deepagents_harness/`](deepagents_harness/) — `orchestrator_workers` and
  `human_in_the_loop`, re-expressed in LangChain's
  [deepagents](https://github.com/langchain-ai/deepagents), side by side
  with their vanilla equivalents in `agentic-design-patterns`. Fully
  offline and tested.
- [`openai_agents_harness/`](openai_agents_harness/) — the same two
  patterns, re-expressed in [the OpenAI Agents SDK](https://github.com/openai/openai-agents-python)
  — a different runtime entirely, not built on LangGraph. Fully offline
  and tested.
- [`agent_framework_harness/`](agent_framework_harness/) — the same two
  patterns, re-expressed in
  [Microsoft Agent Framework](https://github.com/microsoft/agent-framework)
  — its own `Workflow` executor/edge runtime and its own Magentic
  multi-agent orchestration. Fully offline and tested.
- [`strands_harness/`](strands_harness/) — the same two patterns,
  re-expressed in [the Strands Agents SDK](https://github.com/strands-agents/sdk-python)
  — AWS's code-first agent framework, using its Agents-as-Tools pattern
  and its `HumanInTheLoop` intervention. Fully offline and tested.
- [`dapr_agents_harness/`](dapr_agents_harness/) — the same two patterns,
  re-expressed in [Dapr Agents](https://github.com/dapr/dapr-agents) — built
  on Dapr's durable Workflow engine. The one exception to "fully offline":
  it needs a real local Dapr sidecar (see its README) since durable,
  sidecar-backed workflow state is the whole point of using it.

## Quick start

```bash
uv sync
uv run python -m deepagents_harness.run     # one harness, both patterns
uv run python compare.py                    # every installed harness, side by side
uv run pytest -v
```

Both print a **structured trace** — harness name, the fan-out owner, the
runtime-decided subtask count, the gate mechanism, how resume works — in
one shared vocabulary (`shared/trace.py`), so a run lines up cleanly
against its vanilla equivalent in
[`agentic-design-patterns`](https://jithinkk.github.io/agentic-design-patterns/observability/)
and against the other harnesses. `compare.py` stacks all installed
harnesses under aligned headers; a missing one is a labelled skip, not an
error. Add `--otel` (after `uv sync --group otel`) for the same run as an
OpenTelemetry span tree — see [`docs/observability.md`](docs/observability.md).

Runs fully offline against a small deterministic fake chat model — no API
key, no network. Point it at a real model with the `LLM_PROVIDER`
environment variable (`anthropic` or `openai`, plus the matching API key)
when you want to.

## What is deliberately *not* here

**The patterns are not exposed as MCP tools.** It would be technically easy
and conceptually wrong. MCP exists to give an agent *capabilities* — query
this database, deploy this service. These are *architectural shapes*, not
capabilities: a tool that just runs a toy graph sorting a fake support
ticket helps nobody and teaches nothing about the pattern it wraps.

**CLI coding agents are not integrated, only documented.** OpenCode, Goose,
Hermes Agent, Crush, Cline and Aider are harnesses in their own right —
per [`docs/harnesses-and-loops.md`](docs/harnesses-and-loops.md), *"a
harness is not an eighth pattern; it's the composition of these seven."*
They already use these patterns internally; feeding patterns into them
inverts the relationship. And their config surface moves fast enough that
pasted, untestable snippets would be quietly wrong within months — so that
guidance lives in prose, which can say "check the current docs," and not in
this repo, which can't be CI-verified.

**The same two patterns, across every framework here — on purpose.** A
single harness picking one framework mirrors production, where nobody
re-implements a workflow across three frameworks; they pick one. A *repo*
comparing frameworks needs the opposite move: hold the pattern fixed and
vary the machinery underneath it. `orchestrator_workers` and
`human_in_the_loop` were chosen because they're the two patterns every
framework surveyed here expresses natively — see each harness's own
README for the ones that don't fit, and why.

## Adding another harness

The bar, mirroring `agentic-design-patterns`' "everything runs and is
tested with no API key" guarantee:

1. It must be drivable **offline** by a stand-in model. For anything built
   on LangChain this means accepting a `BaseChatModel`, so
   `shared/llm/fake.py`'s `FakeChatModel` drops in. A harness that can only
   talk to a live endpoint belongs in docs, not here. (`dapr_agents_harness`
   is this repo's one accepted exception — not a live endpoint, but a real
   local Dapr sidecar, required to exercise durable workflow state honestly.
   See its README for why that was worth the exception.)
2. Implement only the patterns it expresses **natively**, and document the
   non-fits — those explain more than the fits do.
3. Follow the existing module conventions: `build_agent()` alongside a
   `run.py` exposing `main(...) -> dict`, plus
   `describe_orchestrator_workers(task)` and `describe_human_in_the_loop()`
   that adapt the framework's result into `shared/trace.py`'s
   `OrchestratorTrace` / `HitlTrace` (this is what `compare.py` and the
   `run.py` `__main__` render); and tests under `tests/` that stay green
   with a plain `uv sync`.
4. Add the dependency to `pyproject.toml` and regenerate `uv.lock` — CI
   runs `uv sync --locked` and will fail on drift.

## Project layout

```
ai-harnesses/
├── compare.py                # run one pattern across every installed harness, side by side
├── deepagents_harness/       # patterns under LangChain's deepagents
│   └── tests/
├── openai_agents_harness/    # patterns under the OpenAI Agents SDK
│   └── tests/
├── agent_framework_harness/  # patterns under Microsoft Agent Framework
│   └── tests/
├── strands_harness/          # patterns under the Strands Agents SDK
│   └── tests/
├── dapr_agents_harness/      # patterns under Dapr Agents (needs a real sidecar; see its README)
│   ├── components/           # Dapr component config (in-memory, actor-capable state store)
│   └── tests/
├── shared/                   # vendored LLM factory + fake model + basic tools
│   ├── llm/                  # LangChain-specific -- reused only by deepagents_harness
│   ├── tools/
│   ├── trace.py              # one trace vocabulary every harness reports itself in
│   └── obs.py                # opt-in OpenTelemetry wiring for `--otel`
├── docs/                     # mkdocs site (Harnesses and Loops essay, comparison, observability, one page per harness)
└── mkdocs.yml
```

## License

MIT — see [LICENSE](LICENSE).
