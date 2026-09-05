"""A scripted, deterministic chat model used as the default LLM backend.

Every pattern in this sandbox runs and is unit-tested with this model so
the graphs are fully exercisable with no network access or API key. Each
pattern supplies its own `responder` function that mimics, in a few lines
of Python, what an LLM call at that node would plausibly return. Swap in a
real provider at any time via `shared.llm.factory.get_chat_model(provider=...)`.
"""

from __future__ import annotations

from typing import Any, Callable, Optional, Sequence

from langchain_core.callbacks.manager import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import ConfigDict

Responder = Callable[[list[BaseMessage]], AIMessage]


def echo_responder(messages: list[BaseMessage]) -> AIMessage:
    """Fallback responder: just echoes the last message. Good for smoke tests."""
    last = messages[-1].content if messages else ""
    return AIMessage(content=f"[fake-llm echo] {last}")


class FakeChatModel(BaseChatModel):
    """Deterministic stand-in for `ChatOpenAI` / `ChatAnthropic`.

    `responder` receives the full message history for the call (including
    any `ToolMessage`s from a previous loop iteration) and returns the
    `AIMessage` the "model" should have produced next.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    responder: Responder = echo_responder
    bound_tools: list[Any] = []

    @property
    def _llm_type(self) -> str:
        return "fake-chat-model"

    def bind_tools(
        self,
        tools: Sequence[Any],
        *,
        tool_choice: Optional[str] = None,
        **kwargs: Any,
    ) -> "FakeChatModel":
        # Real chat models use `tools` to constrain generation server-side.
        # Our responders already encode tool-call decisions themselves, so
        # binding just records the tools for introspection/tests.
        return self.model_copy(update={"bound_tools": list(tools)})

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: Optional[list[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        message = self.responder(messages)
        return ChatResult(generations=[ChatGeneration(message=message)])
