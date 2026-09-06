"""Opt-in OpenTelemetry tracing for a harness run (`--otel`).

Off by default and **not** a runtime dependency. The narrated trace each
`run.py` prints (via `shared/trace.py`) is the primary view. `--otel` is
the second one: the same run as a span tree on the OpenTelemetry GenAI
semantic conventions -- and, across this repo, the vendor-neutral axis
that actually makes five different runtimes comparable.

    uv sync --group otel
    uv run python compare.py orchestrator-workers --otel

pulls in Traceloop's OpenLLMetry SDK and wires its spans to a console
exporter (no backend, no API key). Coverage varies by framework: it
auto-instruments LangChain / LangGraph (so `deepagents` is richest) and
the OpenAI / Anthropic clients. Strands, Microsoft Agent Framework and
Dapr Agents each emit their *own* native OpenTelemetry spans -- see
docs/observability.md for turning those on. With the offline fake models
there are no real LLM calls, so the tree is structural, not token-level.

Point it at a real OTLP backend (Jaeger, Arize Phoenix, Langfuse, Grafana
Tempo) by exporting `OTEL_EXPORTER_OTLP_ENDPOINT` and `AIH_OTEL_OTLP=1`.
"""

from __future__ import annotations

import os

_INITED = False


def enable_console_otel() -> None:
    """Initialise OpenLLMetry with a console span exporter. Idempotent."""
    global _INITED
    if _INITED:
        return

    try:
        from traceloop.sdk import Traceloop
    except ModuleNotFoundError as exc:  # pragma: no cover - exercised via CLI
        raise SystemExit(
            "--otel needs the optional 'otel' dependency group:\n"
            "    uv sync --group otel\n"
            "or, with pip:  pip install 'ai-harnesses[otel]'"
        ) from exc

    os.environ.setdefault("TRACELOOP_TELEMETRY", "false")

    if os.getenv("AIH_OTEL_OTLP") == "1":
        Traceloop.init(app_name="ai-harnesses", disable_batch=True, telemetry_enabled=False)
    else:
        from opentelemetry.sdk.trace.export import ConsoleSpanExporter

        Traceloop.init(
            app_name="ai-harnesses",
            exporter=ConsoleSpanExporter(),
            disable_batch=True,
            telemetry_enabled=False,
        )

    _INITED = True
