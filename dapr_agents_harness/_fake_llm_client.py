"""A scripted, deterministic `ChatClientBase` used to drive Dapr Agents offline.

Matches Dapr's own unit-test guidance for the framework generally: mock the LLM
client layer, not the sidecar -- the sidecar (and the durable workflow engine behind
it) is real in this harness; only the model call itself is faked, the same
persistent-`responder` shape `shared/llm/fake.py`'s `FakeChatModel` and the other
harnesses' fakes use.
"""

from __future__ import annotations

from typing import Any, Callable

from dapr_agents.llm.chat import ChatClientBase
from dapr_agents.types.message import AssistantMessage, LLMChatCandidate, LLMChatResponse

Responder = Callable[[list[dict]], AssistantMessage]


class PersistentFakeChatClient(ChatClientBase):
    """Deterministic stand-in for a real `ChatClientBase` (OpenAI/Anthropic/...).

    `responder(messages)` is called on every non-structured turn and returns the
    `AssistantMessage` the "model" should have produced next. Dapr Agents' own
    best-effort conversation-summarization feature (`_summarize_conversation`) makes
    a *structured* call with `response_format` set, on a schedule this harness
    doesn't control -- when that happens, this class returns a minimal instance of
    the requested model directly instead of routing through `responder`, since a
    canned summary carries no information either demo pattern's tests assert on.
    """

    def __init__(self, responder: Responder) -> None:
        self._responder = responder

    def generate(
        self,
        messages: Any = None,
        *,
        input_data: dict | None = None,
        model: str | None = None,
        tools: list | None = None,
        response_format: type | None = None,
        structured_mode: str | None = None,
        stream: bool = False,
        **kwargs: Any,
    ) -> LLMChatResponse:
        if response_format is not None:
            return response_format(**{name: "(offline fake -- no summary generated)" for name in response_format.model_fields})

        message = self._responder(messages)
        return LLMChatResponse(results=[LLMChatCandidate(message=message, finish_reason="stop")])

    @classmethod
    def from_prompty(cls, prompty_source, timeout: int | float | dict = 1500) -> "ChatClientBase":
        raise NotImplementedError("PersistentFakeChatClient does not support from_prompty")
