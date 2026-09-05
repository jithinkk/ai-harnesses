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

-   :material-source-repository:{ .lg .middle } **Under deepagents**

    ---

    Two patterns re-expressed in LangChain's `deepagents` — what a
    framework supplies for free and what it costs you.

    [:octicons-arrow-right-24: Read more](deepagents.md)

</div>

## Quick start

{% include-markdown "../README.md" start="## Quick start" %}
