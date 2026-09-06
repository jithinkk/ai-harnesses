"""A scripted, deterministic `BaseChatClient` used to drive Microsoft Agent Framework offline.

Mixing in `FunctionInvocationLayer` is required, not optional: without it `Agent` logs
"does not support function invoking" and never runs the tool-call loop at all -- verified
directly against the installed package rather than assumed, since `BaseChatClient` alone
doesn't advertise that capability.
"""

from __future__ import annotations

from typing import Any, Callable

from agent_framework import BaseChatClient, ChatResponse, Message
from agent_framework._tools import FunctionInvocationLayer

Responder = Callable[[list[Message]], list[Any]]


class PersistentFakeChatClient(FunctionInvocationLayer, BaseChatClient):
    """Deterministic stand-in for a real `BaseChatClient` (Azure/OpenAI/Ollama/...).

    `responder(messages)` is called on every turn and returns the list of `Content`
    items the "model" should have produced next -- the same persistent-responder shape
    as `shared/llm/fake.py`'s `FakeChatModel` and the openai_agents_harness's
    `PersistentFakeModel`.
    """

    def __init__(self, responder: Responder) -> None:
        super().__init__()
        object.__setattr__(self, "_responder", responder)

    async def _inner_get_response(self, *, messages: list[Message], stream: bool, options: Any, **kwargs: Any) -> ChatResponse:
        contents = self._responder(messages)
        return ChatResponse(messages=Message(role="assistant", contents=contents))
