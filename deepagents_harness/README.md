# The patterns under `deepagents`

[`deepagents`](https://github.com/langchain-ai/deepagents) is LangChain's
agent-harness library, built **on** LangGraph rather than beside it:
`create_deep_agent()` returns a real `CompiledStateGraph`, so `.invoke()`,
`.stream()`, checkpointers and `recursion_limit` all behave exactly as they
do for the hand-built graphs in
[`agentic-design-patterns`](https://github.com/jithinkk/agentic-design-patterns).
That shared substrate is what makes a fair comparison possible — the same
pattern, the same runtime, only a different amount of machinery written by
hand.

Two patterns are implemented here, chosen because deepagents expresses them
natively. The rest are documented below as non-fits, which is the more
useful half of the lesson.

| File | Vanilla equivalent | What deepagents supplies |
|---|---|---|
| `orchestrator_workers.py` | [`patterns/orchestrator_workers`](https://github.com/jithinkk/agentic-design-patterns/tree/main/patterns/orchestrator_workers) | the `task` tool — dynamic subagent fan-out with isolated context |
| `human_in_the_loop.py` | [`patterns/human_in_the_loop`](https://github.com/jithinkk/agentic-design-patterns/tree/main/patterns/human_in_the_loop) | `interrupt_on={...}` — the whole approval gate as one argument |

## What you stop writing

**Fan-out.** Vanilla LangGraph makes it explicit: `continue_to_workers`
returns one `Send("worker", ...)` per subtask, a `worker` node handles each,
and an `operator.add` reducer accumulates results before `synthesizer` runs.
In deepagents you declare subagents and the model delegates by calling
`task`; the isolation, the concurrency and the fan-in are the framework's.

**The approval gate.** Vanilla spreads it across three functions —
`route_after_agent` checks pending calls against
`TOOLS_REQUIRING_APPROVAL`, `request_approval` calls `interrupt(...)`, and
`route_after_approval` either proceeds or injects a denial `ToolMessage`.
deepagents collapses all of it to `interrupt_on={"send_message": True}`.

## What you give up, concretely

- **The resume contract is different, and richer.** Vanilla resumes with a
  bare boolean, `Command(resume=True)`. deepagents expects a decisions
  envelope — `Command(resume={"decisions": [{"type": "approve"}]})` — and
  advertises four decisions rather than two: `approve`, `edit`, `reject`,
  `respond`. `edit` has no equivalent in the hand-built version: a reviewer
  can rewrite the tool's arguments before it runs. Porting between the two
  is not a drop-in swap.
- **The interrupt value is a fixed envelope**, `{"action_requests": [...],
  "review_configs": [...]}`, rather than whatever payload your own node
  chooses to pass to `interrupt(...)`.
- **You get a filesystem whether you asked for one or not.** A default agent
  binds seven filesystem tools — `ls`, `read_file`, `write_file`,
  `edit_file`, `delete`, `glob`, `grep` — plus `task`, before any of your
  own. That is real context spent on every call, and real capability
  surface to think about if the model is untrusted. The vanilla graphs bind
  exactly the tools you hand them.

## Patterns that don't fit, and why

Verified against deepagents 0.7.9 rather than assumed:

- **`prompt_chaining`** — a fixed sequence of model calls with a
  *programmatic* gate between them. deepagents is an agent: the model owns
  the order of operations. There's no supported way to say "call A, then
  evaluate this Python condition, then call B" — you'd be asking an agent
  framework to act as a workflow engine, and losing the compile-time
  ordering guarantee that makes `prompt_chaining` worth using.
- **`parallelization`** — needs a branch count fixed in code at graph-build
  time. `task` fan-out is model-decided at runtime, and the results return
  as tool messages the model reads rather than through a reducer you
  control. That's `orchestrator_workers` by construction, which is exactly
  why that one is implemented here and this one isn't.
- **`routing`** — a single classification into a fixed branch set. Subagents
  can approximate it, but nothing guarantees the model routes exactly once
  to exactly one branch; you'd be paying agent-loop unpredictability for a
  decision a conditional edge makes deterministically.
- **`evaluator_optimizer`** — a generate⇄evaluate cycle with a code-enforced
  iteration cap. `recursion_limit` bounds total steps, not rounds of
  refinement against explicit pass/fail criteria.
- **`react_agent`** — not a non-fit so much as a tautology: deepagents *is*
  a ReAct-style tool loop with extras. Reimplementing it here would show
  nothing the two above don't.

Note that these are all cases where the vanilla pattern's value *is* its
compile-time guarantee. That's the through-line: a framework that hands you
agency for free is a poor place to put a workflow whose whole point is not
having any.

## Run it

```bash
uv sync
uv run python -m deepagents_harness.run
```

Runs fully offline against `FakeChatModel` — no API key, no network.
`create_deep_agent`'s `model` parameter is typed `str | BaseChatModel |
None`, so the fake model drops straight in.

## Test it

```bash
uv run pytest deepagents_harness -v
```
