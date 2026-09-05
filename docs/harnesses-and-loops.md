# Harnesses and Loops

The seven patterns in this repo are graph shapes: how nodes connect, when
they branch, when they loop. This page is about the layer above that — how
a real coding agent (Claude Code, and agent harnesses like it) wraps those
shapes into something that runs safely, for hours, across sessions, with a
human able to step in, its behavior checked before it ships. It's the "so
what does this look like outside a demo repo" page: the loop, the harness
around it, the different shapes a harness itself can take and what should
guide picking one, and four things every production agent system needs
beyond the loop — memory, guardrails, tool integration at scale (MCP),
and evals (context engineering is folded into memory below, since it's
largely the same problem).

**This page is deliberately not a proposal for eight more patterns.** The
seven graphs stay the focus of this repo; what follows is what a
production system builds *around* them, with an honest accounting of how
much of that this repo does and doesn't show.

## Two words, precisely

**The agent loop** is the literal cycle: observe the current state, decide
what to do next, act, observe the result, repeat until done. It's old —
this is the [ReAct](https://arxiv.org/abs/2210.03629) idea from 2022 — and
it's small enough to fit in one graph.
[`react_agent`](https://github.com/jithinkk/agentic-design-patterns/tree/main/patterns/react_agent)
*is* this loop, about as bare as it gets: one node calls the model, a
conditional edge checks for a tool call, a tool node runs it, and control
returns to the model. Nothing else.

**The harness** is everything wrapped around that loop that a bare
`while True: call_model()` doesn't give you for free: what tools exist and
what they're allowed to touch, how a human gets a say before something
irreversible happens, how the agent keeps working when a single context
window isn't enough, how a big task gets split across many loops running
at once instead of one. A harness can run the same underlying loop a
thousand times with a thousand different sets of scaffolding around it.

This distinction matters because **the loop is what these seven patterns
implement, and the harness is what production agent systems build around
them.** Confusing the two is why "just add a while loop" and "build a
production coding agent" sound like the same problem and aren't.

## What a real harness adds around the loop

A few concrete, sourced examples of what sits between "the model wants to
call a tool" and "the tool call actually runs" in a real system:

- **The harness executes tools, never the model directly.** The model
  returns a *structured* tool call; the harness validates the schema,
  checks permissions, executes, and injects the result back into the
  loop. This is the mechanism that stops a prompt injection from becoming
  arbitrary code execution — the model can *ask* for anything, but only
  the harness decides what actually runs. `human_in_the_loop`'s approval
  gate in this repo is a small, explicit version of exactly this checkpoint.
- **Hooks stack into dispatchers, dispatchers into skills, skills into
  agents, agents into workflows.** Claude Code's own architecture is
  documented as roughly 30 lifecycle events (hooks) that compose this
  way — the loop stays the same shape at every layer, but each layer adds
  a place to intervene before or after a step.
- **Subagents get their own clean context window.** A parent agent
  dispatches a scoped task to a subagent, which explores deeply in
  isolation and returns a compact summary — not its full transcript —
  to the parent. `orchestrator_workers` in this repo is the graph-level
  version of this: fan out to N workers, each gets only its own subtask,
  the synthesizer sees only their results, not their internal reasoning.
  In 2026, Claude Code extended this with *dynamic* orchestration — the
  model generates orchestration scripts that fan out to tens or hundreds
  of parallel subagents with adversarial verification between them,
  rather than a fixed, code-defined worker count.
- **Long-running work survives context-window boundaries.** Anthropic's
  documented approach for multi-session agent work: an initializer agent
  sets up the environment once and writes a structured task list; a
  coding agent is then woken up repeatedly, each session making
  incremental progress, running tests, leaving a progress note for the
  *next* session, and committing. The mechanism underneath is the same
  one `human_in_the_loop` uses here for a single pause — a checkpointer
  persisting state between separate `invoke()` calls — just used across
  days instead of across one approval.

## Where each pattern shows up in a real harness

| Pattern | What it looks like inside a real agent harness |
|---|---|
| `react_agent` | The core loop itself — every tool-calling agent harness runs some version of this underneath everything else |
| `human_in_the_loop` | The permission/approval layer — Claude Code's own tool-permission prompts are this exact mechanism |
| `orchestrator_workers` | Subagent dispatch with isolated context — Claude Code's `Task` tool and its dynamic parallel-subagent orchestration |
| `parallelization` | Independent tool calls issued in a single turn, or independent checks (lint + test + typecheck) run concurrently |
| `routing` | The dispatch/classification layer that decides which skill, subagent, or specialized prompt handles a request |
| `evaluator_optimizer` | Self-verification loops — a harness re-checking its own output, or the "adversarial verification" step between parallel subagents |
| `prompt_chaining` | A fixed multi-step pipeline a harness runs for one well-defined job (e.g. a slash command with several deterministic stages) |

None of these patterns are *replaced* by harness concepts — they're the
pieces a harness assembles. A harness is not an eighth pattern; it's the
composition of these seven (plus the gaps below) into something that runs
unattended, safely, for longer than one context window.

## Different harnesses, and what guides picking one

Everything above this point — the tool-execution boundary, hooks
stacking into dispatchers, subagent isolation, cross-session
persistence — came from one concrete harness archetype: an interactive
CLI/coding-agent harness like Claude Code. Not every production agent
system is shaped like that. Different deployment contexts produce
genuinely different harness shapes, assembling the same seven patterns
differently depending on who — or what — is on the other end of the loop.

**Interactive CLI/coding-agent harness.** Claude Code itself, as
described throughout this page. A human is present and attentive turn by
turn, so approval for a risky action can be a blocking prompt — the exact
mechanism `human_in_the_loop`'s `interrupt()` demonstrates here. Leans on
`react_agent` for the core loop, `human_in_the_loop` for the permission
layer, and `orchestrator_workers` for subagent dispatch.

**Chat/product assistant harness.** A customer-facing assistant embedded
in a product — turn-based, session-scoped memory, a tight per-turn
latency budget. Nobody is watching each individual tool call the way a
developer watches Claude Code's prompts, so tool access is policy-gated
up front (a fixed allowlist decided at design time) rather than gated
per-call with a blocking pause. Leans on `routing` for intent
classification and `prompt_chaining`/`parallelization` for structured
sub-tasks; `react_agent` only within a toolset that's already been
vetted as safe to run unsupervised.

**Autonomous/scheduled harness.** No human present at run time at all —
a cron-triggered agent, a monitoring bot, a routine that wakes itself up
on a schedule. This very repo's development process used a live instance
of exactly this archetype: several PR check-ins in this session ran as
scheduled routines that fired unattended, checked CI/mergeability, and
either acted or silently re-armed for the next check — with no one
watching any single firing. This archetype can't use a blocking
`interrupt()` the way `human_in_the_loop` does, because there's no one to
resume it; it needs the decision made *in advance* instead — an
auto-approve/auto-deny policy, with escalation via a notification rather
than a paused run. Guardrails matter more here than anywhere else, since
unattended plus open-ended is the highest-risk combination a harness can
have. Leans on `prompt_chaining`/`orchestrator_workers`/
`evaluator_optimizer` — fixed, testable shapes — over open-ended
`react_agent`.

**Batch/pipeline harness.** A high-volume, cost-sensitive offline job —
document processing across thousands of records, say. Idempotency and
retry-safety matter more than flexibility, and cost is `per-item ×
volume`, which makes an unbounded `react_agent` per item the single most
expensive shape available at scale. Leans hardest on the fixed-shape
workflow patterns specifically *because* their cost is predictable in
code, not despite it.

**Multi-agent orchestration harness.** A top-level coordinator
dispatching to many specialized subagents — Claude Code's own dynamic
orchestration extension (described above) or a swarm-style system more
broadly. Needs isolation between subagents' context and an explicit
reduction/aggregation step; cost and latency both multiply with subagent
count. `orchestrator_workers` is the structural backbone; each worker can
internally be any of the other six patterns.

**What guides picking one** — the harness-level version of the
pattern-level question `architecture-overview.md`'s decision tree asks:

- **Is a human present and attentive at run time?** Interactive harnesses
  can use blocking `interrupt()`-based approval; autonomous ones can't,
  and need policy-based guardrails decided in advance instead.
- **What's the latency budget?** Sub-second/turn-based rules out
  unbounded `react_agent` loops; offline/batch tolerates them far better.
- **What's the volume and cost sensitivity?** A one-off task can afford
  flexibility; a thousand-per-day task needs the cheapest fixed-shape
  pattern that still works.
- **What's the blast radius of a mistake?** Any harness with real
  side-effecting tools needs an approval or policy gate somewhere —
  whether that's a blocking `interrupt()` (interactive) or a
  pre-authorized allowlist plus an audit log (autonomous).
- **How long does a single unit of work run?** Single-request harnesses
  need no persistence; multi-session or multi-day harnesses need the same
  checkpointer mechanism `human_in_the_loop` already demonstrates here,
  just stretched across a longer boundary.

This is the same instinct as `architecture-overview.md`'s rule of thumb —
prefer the most constrained pattern that still solves the problem — one
level up: prefer the most constrained *harness* that still fits how the
system will actually run.

## Memory (and context engineering — largely the same problem)

Two different things share the word "memory," and conflating them causes
real design mistakes:

- **Short-term / working memory** — the current task's state while it's
  in progress: the `messages` list in every pattern here, the accumulated
  `worker_results` in `orchestrator_workers`, the `iteration` count in
  `evaluator_optimizer`. Every pattern in this repo has this; it's just
  the graph's state.
- **Long-term memory** — what persists *across* separate runs: what this
  user asked last week, what the agent learned that should inform the
  next unrelated task. **No pattern in this repo has this.** Every
  `run.py` starts from an empty `messages` list; nothing is read from or
  written to anywhere outside that one process's memory.

Anthropic's own current guidance names three techniques for the closely
related problem of the context window filling up with stale or irrelevant
history as a single task runs long:

- **Compaction** — summarize a conversation nearing its context limit and
  reinitiate with the summary, maximizing recall first, then trimming for
  precision.
- **Structured note-taking** — the agent writes notes to storage outside
  the context window and pulls them back in later, cheap persistent memory
  without keeping everything in-context.
- **Sub-agent isolation** — already covered above; it's a context-engineering
  technique as much as an orchestration one, since its real benefit is
  keeping the parent's context window clean.

`react_agent`'s `messages` list in this repo grows without bound — no
compaction, no trimming, no external notes. That's a known, documented gap
(see its README's "production readiness" section), and it's the most
consequential one left in this repo: every source consulted for this page
treats context engineering as the dominant challenge in production agents
once tool use and multi-step reasoning are in play, more than pattern
choice itself.

**Don't confuse this with `human_in_the_loop`'s checkpointer.** That
checkpointer persists state so one paused run can resume — it's plumbing
for a single interrupted task, not a long-term memory store. Long-term
memory needs its own storage (a database row per user, a vector store for
semantic recall) read at the *start* of a run and written at the *end* —
structurally different from pausing mid-run. A minimal sketch of what
adding it to `react_agent` would look like, without building a whole new
pattern for it:

```python
# Long-term memory, sketched (not implemented in this repo):
checkpointer = PostgresSaver(...)  # durable, not the in-memory one HITL uses
app = builder.compile(checkpointer=checkpointer)

config = {"configurable": {"thread_id": f"user-{user_id}"}}  # stable per user, not per run
result = app.invoke({"messages": [HumanMessage(content=task)]}, config)
# Next call with the same thread_id continues the same conversation history --
# that's long-term memory, using the exact same LangGraph primitive
# human_in_the_loop already uses for a different reason.
```

## Guardrails

Current production guidance names four places a guardrail belongs: input,
tool calls, tool responses, and final output. This repo has real,
concrete instances at two of the four — and the other two are named gaps,
not oversights:

| Guardrail point | In this repo | Missing |
|---|---|---|
| **Input** | Nothing — every pattern trusts its input string as-is | No length cap, no content filtering on what a user submits before it reaches a graph at all |
| **Tool call** | `human_in_the_loop`'s approval gate — a tool call doesn't execute until a human clears it | Only gates `send_message`; a production system would classify every tool by risk, not hand-pick one |
| **Tool response / execution** | `calculator`'s bit-length bound and expression-length cap (`shared/tools/basic.py`) — this is a real guardrail this repo shipped after a real bug: a single call like `99999999**99999999` hung the process indefinitely before the fix | No sandboxing for tools that touch the filesystem or network (none currently do, but `react_agent`'s README flags this as the pattern to watch) |
| **Output** | Nothing | No schema/content check on the final answer before it's returned |

**Recursion limit — closed.** Both agent-loop patterns' `run.py` now set
`config={"recursion_limit": N}` explicitly (default 25, LangGraph's own
implicit default made a considered choice instead) rather than relying on
the framework default silently. Verified empirically, not assumed: a
runaway tool-calling loop genuinely raises `GraphRecursionError` at the
limit (proven with a scripted infinite-tool-call test in each pattern's
test suite), and `interrupt()`/resume budgets independently per
`invoke()` call rather than cumulatively, so a slow human approval never
eats into either budget. The graph itself still has no compile-time cap
— LangGraph doesn't support one — so calling `build_graph().invoke(...)`
directly, bypassing `run.py`, is still unbounded; see each pattern's
`graph.py` for that caveat in context. A wall-clock timeout is still a
separate, unclosed gap — a `recursion_limit` bounds *steps*, not *time*
if a single step (an unusually slow model call) hangs.

The tool-call and tool-response rows above assume tools you wrote and
reviewed yourself, like this repo's `shared/tools/basic.py`. That
assumption stops holding the moment tools come from somewhere else —
see below.

## Tool integration at scale: MCP

**Half implemented, deliberately.** The distinction is direction:

- **Serving** this repo's own tools over MCP — implemented, in
  [`shared/tools/mcp_server.py`](https://github.com/jithinkk/agentic-design-patterns/blob/main/shared/tools/mcp_server.py).
  A stdio server exposing the four tools in `shared/tools/basic.py`, so
  any MCP-speaking harness can call them. It's unit-tested offline
  (`MCPServer.list_tools()` and `.call_tool()` are directly awaitable, so
  no transport, subprocess or socket is needed in a test) and its
  optional dependency lives in the `harnesses` group.
- **Consuming** third-party MCP tool servers — still not implemented, for
  the reason given below. That's the direction that would cost this repo
  its offline guarantee.

Serving is cheap and honest because the tools are ours and already
tested; consuming means depending on someone else's live server. The rest
of this section is about the consuming side.

**What MCP is, briefly.** The [Model Context
Protocol](https://modelcontextprotocol.io/) is a standardized
client-server protocol for exposing tools (and resources, and prompts) to
LLM agents. Instead of every agent framework needing its own hand-rolled
wrapper per external system, a tool integration is written once as an MCP
server, and any MCP-compatible client — Claude Code included, at its own
tool-integration boundary — can discover and call it the same way.

**What changes in this repo's patterns, and what doesn't.** Nothing about
the *graph shape*. Verified directly against `langchain-mcp-adapters`'
own usage example — its LangGraph wiring is `StateGraph` +
`MessagesState` + `ToolNode` + `tools_condition`, the exact same four
pieces `react_agent/graph.py` uses. The only line that changes is where
the tool list comes from:

```python
# This repo's react_agent (shared/tools/basic.py, local & hand-written):
from shared.tools.basic import ALL_TOOLS
builder.add_node("tools", ToolNode(ALL_TOOLS))

# The MCP equivalent (sketched, not in this repo):
from langchain_mcp_adapters.client import MultiServerMCPClient
client = MultiServerMCPClient({
    "internal-crm": {"url": "https://mcp.internal/crm", "transport": "http"},
    "filesystem": {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "."], "transport": "stdio"},
})
tools = await client.get_tools()  # discovered at runtime, not hand-written
builder.add_node("tools", ToolNode(tools))
# Everything else -- the agent node, tools_condition, the edges -- is unchanged.
```

That's the whole point of a protocol boundary: `react_agent`,
`human_in_the_loop`, and `orchestrator_workers` don't need to know or
care whether a tool is a three-line local Python function or a call to a
remote MCP server. The pattern shapes in this repo are already correct
for both.

**Why this repo doesn't consume MCP servers.** Every pattern here is built to
run fully offline, deterministically, against a scripted fake model, with
no network access required to clone-and-test — that's the whole premise
behind `shared/llm/fake.py`. MCP is a live client-server protocol; there's
no equally lightweight way to fake an entire external tool server the way
`FakeChatModel` fakes an LLM call. Wiring MCP in would mean either a real
running server as a test dependency (breaking the "no network access"
guarantee every pattern currently has) or a second, parallel fake-server
layer just for MCP — a maintenance cost this teaching repo doesn't take on.

**Why this matters more than an integration convenience, per the
Guardrails section above.** MCP tool servers are, as of 2026, a genuinely
dangerous unaudited surface at real production scale — this isn't a
hypothetical:

- An April 2026 supply-chain report identified a systemic vulnerability
  in MCP's STDIO transport affecting **150 million downstream package
  downloads**, across over 7,000 publicly accessible MCP servers, with an
  estimated 200,000 vulnerable instances.
- A July 2026 measurement study of internet-facing MCP servers found
  **91.8% of 640 audited production servers had no OAuth**, and 687
  instances exposed unrestricted shell tool access.

Every tool call from an MCP server lands at exactly the "tool call" and
"tool response" rows in the Guardrails table above — except now the tool
wasn't written by you, wasn't reviewed by you, and its server may not
even authenticate its own callers. This is precisely the scenario
`human_in_the_loop`'s approval gate exists for, and it argues for
inverting this repo's toy version of it: `TOOLS_REQUIRING_APPROVAL` here
is a hand-picked allowlist of one tool because there are only four tools
total and we wrote all of them. Against a dynamically-discovered set of
MCP tools from third-party servers, the safe default flips — gate
everything by default, and explicitly allowlist only tools from servers
you've actually reviewed.

### Which CLI harnesses you can point at an MCP server

The archetype table earlier in this page is about harness *shapes*. This
is the concrete roster of open-source **interactive CLI/coding-agent**
harnesses as of writing, and how you'd attach a tool server like this
repo's to each.

MCP is close to universal among them, which is what makes writing one
server worthwhile rather than N integrations:

| Harness | Project | Config format | MCP |
|---|---|---|---|
| OpenCode | `sst/opencode` | JSON (`opencode.json`) | yes |
| Goose | `block/goose` | YAML | yes — MCP *is* its extension model |
| Hermes Agent | `NousResearch/hermes-agent` | YAML | yes |
| Crush | `charmbracelet/crush` | shell-style rc file | yes — stdio, http, sse |
| Cline | `cline/cline` | JSON | yes |
| Aider | `Aider-AI/aider` | YAML | **no** |

Every one of them takes the same two things — a command to run and its
arguments — so attaching the server in this repo means pointing a harness
at `python -m shared.tools.mcp_server`. Only the surrounding config key
differs.

**Aider is the exception**: it has no MCP support, so tools reach it as
something you run yourself and paste, or a file you `--read` into the
chat. Worth knowing before planning an integration around it.

**Deliberately no config snippets here.** This surface moves fast enough
that pasted blocks would be quietly wrong within months, and unlike the
code in this repo they can't be CI-verified — while writing this page
alone, OpenCode was mid-migration between GitHub orgs, Crush had
deprecated its JSON config for an rc file, and OpenHands had renamed
itself and split its agent into a separate SDK. Check each project's
current docs for the exact key; the shape (a command plus args) is the
part that has stayed stable.

**Name Hermes Agent in full.** "Hermes" alone is ambiguous: Nous Research
also publishes the Hermes 3/4 open-weight *models* (a different thing —
notable for an XML tool-call convention, not a harness), and Meta's
JavaScript engine shares the name.

One caveat on testing: of these, none offers a stub-model mode comparable
to this repo's `FakeChatModel`, so an end-to-end "harness drives the
tools" check needs either a real API key or a local OpenAI-compatible
endpoint. That's exactly why the integration this repo ships is the
*server* — which is testable in-process — rather than harness configs,
which are not.

## Evals — not the same thing as `evaluator_optimizer`

These two ideas share a name and get confused constantly:

- **`evaluator_optimizer` (the pattern in this repo)** runs *inside* one
  task, at *runtime*: generate a solution, grade it, revise, repeat until
  it passes or a cap is hit. It never leaves the graph.
- **Evals (a production practice)** run *outside* any single task, at
  *development/CI time*: a fixed set of inputs with known-good properties,
  run against the system on every change, scored, tracked over time to
  catch regressions before they ship. An eval suite tests the *system*;
  `evaluator_optimizer` is one *component* a system under eval might contain.

This repo already has something eval-shaped, worth naming explicitly: the
23 tests across `patterns/*/tests/` are a small, deterministic eval suite
— fixed inputs, asserted properties, run on every change. That's the
right shape. What makes it a demo rather than a production eval suite:

- **It only tests against the fake LLM.** Every assertion is exact-match
  against `FakeChatModel`'s scripted output. Nothing here has ever
  verified that pointing a pattern at a real `gpt-4o-mini` or
  `claude-sonnet-5` call produces sensible behavior — the fake responder
  encodes *assumptions* about what a real model would do, never checked
  against one.
- **Exact-match doesn't survive contact with a real, non-deterministic
  model.** A real eval suite needs rubric- or LLM-judge-based scoring
  ("does the response mention the required keyword and stay under N
  words?") rather than string equality, since the same prompt against a
  real model won't return byte-identical output twice.
- **No regression tracking over time.** Pytest tells you pass/fail right
  now; it doesn't track whether `routing`'s classification accuracy on a
  held-out set is drifting release over release, which is what an eval
  suite is actually for once a pattern is running against a real model in
  production.

Scalable automation needs both halves this repo currently has only one of:
deterministic tests that a bug can't silently break (this repo has that,
against the fake model), and real-model evals that catch the much larger
class of failures — bad prompts, model upgrades changing behavior, edge
cases the fake responder never encoded — that only show up against a real
model (this repo has none of that).

## Sources

- [ReAct: Synergizing Reasoning and Acting in Language Models](https://arxiv.org/abs/2210.03629) — the original loop
- [Building Effective AI Agents (Anthropic, Dec 2024)](https://www.anthropic.com/engineering/building-effective-agents) — the taxonomy this repo's other six patterns follow
- [Effective context engineering for AI agents (Anthropic)](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) — compaction, structured note-taking, sub-agent architectures
- [Effective harnesses for long-running agents (Anthropic)](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) — the initializer-agent / coding-agent / progress-artifact pattern for multi-session work
- [Harness engineering for coding agent users (Martin Fowler)](https://martinfowler.com/articles/harness-engineering.html)
- [awesome-harness-engineering](https://github.com/ai-boost/awesome-harness-engineering) — curated list of harness engineering tools and patterns
- [15 Production Design Patterns for Agentic AI Systems — Reliability Catalog 2026](https://medium.com/@wasowski.jarek/building-reliable-ai-agents-catalog-of-15-production-patterns-agentic-design-patterns-3cff554cbb70) — the four-point guardrail model (input / tool call / tool response / output) and bounded execution
- [Model Context Protocol](https://modelcontextprotocol.io/) — the protocol itself
- [langchain-mcp-adapters](https://pypi.org/project/langchain-mcp-adapters/) — the MCP↔LangGraph bridge whose usage example this page's code sketch is verified against
- [6 Critical Challenges Facing the MCP in 2026 (Medium)](https://medium.com/@MattLeads/6-critical-challenges-facing-the-mcp-in-2026-06258e914402) — the "MCP Paradox": integration speed outpacing security guardrails
- [A First Measurement Study on Authentication Security in Real-World Remote MCP Servers](https://arxiv.org/pdf/2605.22333) — the 91.8%-no-OAuth / unrestricted-shell-access findings cited above
