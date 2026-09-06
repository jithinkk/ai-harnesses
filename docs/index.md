# AI Harnesses

A DIY exploration of AI agent harnesses and trade-off analysis. Each harness
here re-expresses patterns from
[`agentic-design-patterns`](https://github.com/jithinkk/agentic-design-patterns)
— hand-built LangGraph implementations of Anthropic's agentic design
patterns — through a real framework, so you can see side by side what the
framework supplies for free and what it costs you.

!!! tip "No API key required"
    Everything here runs and is unit-tested **offline**, against a small
    deterministic fake chat model. Point it at a real model with one
    environment variable when you want to.

[:octicons-rocket-24: Quick start](#quick-start){ .md-button .md-button--primary }
[:fontawesome-brands-github: View on GitHub](https://github.com/jithinkk/ai-harnesses){ .md-button }

## What's here

<div class="grid cards" markdown>

-   :material-cog-outline:{ .lg .middle } **Harnesses and Loops**

    ---

    The conceptual essay behind this repo: the agent loop vs. the harness
    around it, harness archetypes, and what production adds beyond the
    graphs — memory, guardrails, MCP tool integration, and evals.

    [:octicons-arrow-right-24: Read more](harnesses-and-loops.md)

</div>

Five harnesses re-express the same two patterns — `orchestrator_workers`
and `human_in_the_loop` — through five different frameworks:

| Harness | Summary |
|---|---|
| [deepagents](deepagents.md) | LangChain's agent-harness library, built on LangGraph |
| [OpenAI Agents SDK](openai-agents.md) | OpenAI's own runtime — handoffs, guardrails, tool-approval |
| [Microsoft Agent Framework](agent-framework.md) | Workflow executors/edges + Magentic multi-agent orchestration |
| [Strands Agents SDK](strands.md) | AWS's code-first framework — Agents-as-Tools, `HumanInTheLoop` |
| [Dapr Agents](dapr-agents.md) | Built on Dapr's durable Workflow engine — needs a real sidecar |

[:octicons-arrow-right-24: See the full comparison](comparison.md) — runtime
substrate, delegation mechanism, HITL mechanism, and offline-fake strategy,
side by side.

## Quick start

{% include-markdown "../README.md" start="## Quick start" %}
