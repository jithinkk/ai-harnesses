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

## Quick start

```bash
uv sync
uv run python -m deepagents_harness.run
uv run pytest -v
```

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

**Only one framework per harness.** Nobody re-implements a single workflow
across three frameworks in production; they pick one. A second framework
would multiply maintenance without changing the lesson.

## Adding another harness

The bar, mirroring `agentic-design-patterns`' "everything runs and is
tested with no API key" guarantee:

1. It must be drivable **offline** by a stand-in model. For anything built
   on LangChain this means accepting a `BaseChatModel`, so
   `shared/llm/fake.py`'s `FakeChatModel` drops in. A harness that can only
   talk to a live endpoint belongs in docs, not here.
2. Implement only the patterns it expresses **natively**, and document the
   non-fits — those explain more than the fits do.
3. Follow the existing module conventions: `build_agent()` alongside a
   `run.py` exposing `main(...) -> dict`, and tests under `tests/` that stay
   green with a plain `uv sync`.
4. Add the dependency to `pyproject.toml` and regenerate `uv.lock` — CI
   runs `uv sync --locked` and will fail on drift.

## Project layout

```
ai-harnesses/
├── deepagents_harness/   # patterns under LangChain's deepagents
│   └── tests/
├── shared/               # vendored LLM factory + fake model + basic tools
│   ├── llm/
│   └── tools/
├── docs/                 # mkdocs site (Harnesses and Loops essay, deepagents)
└── mkdocs.yml
```

## License

MIT — see [LICENSE](LICENSE).
