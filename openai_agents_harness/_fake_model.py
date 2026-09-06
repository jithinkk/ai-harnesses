"""A scripted, deterministic `Model` used to drive the OpenAI Agents SDK offline.

Unlike `agents.testing.model.ScriptedModel` (a queue of one-shot steps, consumed one per
call), this keeps a single persistent `responder` around for the life of the agent --
the same shape as `shared/llm/fake.py`'s `FakeChatModel` in the deepagents harness.
`responder` receives the full item history for the call (`agents`' "Responses API"
format: plain dicts for messages and tool results, `ResponseFunctionToolCall` for a
model-emitted tool call) and returns the list of output items the "model" should have
produced next. Build items with `agents.testing.model.assistant_message`/`function_call`
-- the SDK's own officially-provided test helpers -- rather than hand-rolling the
Responses API's item shapes.
"""

from __future__ import annotations

from typing import Any, Callable

from agents.models.interface import Model, ModelResponse
from agents.usage import Usage

Responder = Callable[[str | None, list[Any]], list[Any]]


class PersistentFakeModel(Model):
    """Deterministic stand-in for a real OpenAI/other provider `Model`.

    `responder(system_instructions, input)` is called on every turn, orchestrator and
    delegated subagent alike -- `system_instructions` is how a responder tells them apart
    (see `orchestrator_workers.py`'s `_RESEARCHER_MARKER`), the same idiom the deepagents
    harness uses for the same reason.
    """

    def __init__(self, responder: Responder) -> None:
        self._responder = responder

    async def get_response(
        self,
        system_instructions: str | None,
        input: str | list[Any],
        model_settings: Any,
        tools: list[Any],
        output_schema: Any,
        handoffs: list[Any],
        tracing: Any,
        *,
        previous_response_id: str | None,
        conversation_id: str | None,
        prompt: Any,
    ) -> ModelResponse:
        items = input if isinstance(input, list) else [{"role": "user", "content": input}]
        output = self._responder(system_instructions, items)
        return ModelResponse(output=output, usage=Usage(), response_id="fake-response")

    async def stream_response(self, *args: Any, **kwargs: Any):
        # Not exercised by this harness -- Runner.run() (non-streaming) is all it demos.
        raise NotImplementedError("PersistentFakeModel does not support streaming")
        yield  # pragma: no cover -- makes this an async generator to satisfy Model's signature
