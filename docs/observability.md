# Observability

Two views of a harness run. The **narrated trace** is on by default and
needs nothing installed. The **`--otel` span tree** is the opt-in second
view — and, across five runtimes, the vendor-neutral axis that makes them
actually comparable.

## 1. The narrated trace (default)

Every `*_harness/run.py` and `compare.py` prints the same structured block,
built from `shared/trace.py`:

```console
$ uv run python -m strands_harness.run

strands · orchestrator-workers
────────────────────────────────────────────────────────────────
  fan-out owner      : Agents-as-Tools — a plain @tool runs a fresh Agent per call, one call per subtask
  subtasks (runtime) : 3 — pricing, onboarding, support quality
  isolation          : a new Agent() per research() call keeps each subagent's context isolated
  synthesis          : orchestrator merges the 3 returned reports
  ...

strands · human-in-the-loop
────────────────────────────────────────────────────────────────
  gate owner   : HumanInTheLoop(allowed_tools=[...]) — an inverted, allow-list intervention
  gate fired   : yes → run PAUSED before the tool ran
  decision     : APPROVED → tool ran
  resume       : decided inline by the `ask` callback wired in up front — no separate resume call
  paused state : in-memory
```

The fields are identical across harnesses on purpose — `fan-out owner`,
`subtasks (runtime)`, `gate owner`, `resume`, `paused state` — so two
harnesses diff cleanly and the vocabulary matches the vanilla repo's
[narrated traces](https://jithinkk.github.io/agentic-design-patterns/observability/).
`compare.py` stacks all installed harnesses under aligned headers.

## 2. The OpenTelemetry span tree (`--otel`)

```bash
uv sync --group otel
uv run python compare.py orchestrator-workers --otel
```

`--otel` initialises [Traceloop's OpenLLMetry
SDK](https://github.com/traceloop/openllmetry) and wires its spans, on the
[OpenTelemetry GenAI semantic
conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/), to a
console exporter (`shared/obs.py`) — no backend, no API key. Point it at a
real OTLP backend ([Arize Phoenix](https://github.com/Arize-ai/phoenix),
[Langfuse](https://langfuse.com/), Jaeger, Grafana Tempo) with
`OTEL_EXPORTER_OTLP_ENDPOINT` + `AIH_OTEL_OTLP=1`.

### Coverage varies by framework — and that's a finding

| Harness | What `--otel` (OpenLLMetry) captures | Native OTel of its own |
|---|---|---|
| deepagents | Full: `langgraph` root, one span per node, `create_agent` / `chat` spans with `gen_ai.*` attributes — it's LangChain under the hood, which OpenLLMetry instruments directly | (via LangChain instrumentation) |
| OpenAI Agents SDK | The underlying OpenAI client calls; the SDK's own agent/handoff spans need its built-in tracing | Yes — [built-in tracing](https://openai.github.io/openai-agents-python/tracing/) with an OTel processor |
| Microsoft Agent Framework | Little from OpenLLMetry directly | Yes — emits OTel spans natively; enable via its `observability` setup |
| Strands Agents SDK | Little from OpenLLMetry directly | Yes — [OTel support built in](https://strandsagents.com/latest/user-guide/observability-evaluation/observability/) |
| Dapr Agents | Little from OpenLLMetry directly | Yes — Dapr emits OTel across the sidecar |

With the offline fake models there are no real model round-trips, so the
tree is **structural** (agent/node/tool spans and their nesting), not
token-level. Run a harness against a real provider (`LLM_PROVIDER=anthropic`
+ key) to get `gen_ai.usage.*` and latency on the `chat` spans.

The lesson the span tree teaches that the narrated trace can't: a
hand-built LangGraph pattern and deepagents share one instrumentation
story (instrument LangChain, done); each of the other four frameworks
brings its *own* OTel integration you'd have to learn and wire. "Let a
framework supply the pattern" also means "adopt that framework's
observability", and those are five different adoptions.

## Which one do I want?

- **Understanding a framework's mechanism, or diffing two** → the narrated
  trace / `compare.py`.
- **What production sees** — span nesting, latency, token cost, a tree you
  can ship to a backend → `--otel`.
- **A vendor-neutral axis to compare frameworks on** → `--otel`, accepting
  that each framework's native OTel goes deeper than OpenLLMetry's
  cross-cutting instrumentation does.
