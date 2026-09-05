"""Single place every pattern gets its chat model from.

Provider is chosen, in order: an explicit `provider` argument, the
`LLM_PROVIDER` env var, then auto-detection from whichever API key is set.
With nothing configured it falls back to the offline `FakeChatModel`, so
every pattern is runnable and testable without an API key.
"""

from __future__ import annotations

import os
from typing import Any, Optional

from langchain_core.language_models.chat_models import BaseChatModel

from shared.llm.fake import Responder, echo_responder


def _auto_detect_provider() -> str:
    if os.getenv("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    return "fake"


def get_chat_model(
    provider: Optional[str] = None,
    *,
    responder: Optional[Responder] = None,
    temperature: float = 0.0,
    **kwargs: Any,
) -> BaseChatModel:
    """Return a `BaseChatModel` for the requested provider.

    `responder` is only used by the "fake" provider (see `shared.llm.fake`);
    it's ignored for real providers so callers can pass it unconditionally.
    """
    provider = (provider or os.getenv("LLM_PROVIDER") or _auto_detect_provider()).lower()

    if provider == "fake":
        from shared.llm.fake import FakeChatModel

        return FakeChatModel(responder=responder or echo_responder)

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        model = kwargs.pop("model", os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5"))
        return ChatAnthropic(model=model, temperature=temperature, **kwargs)

    if provider == "openai":
        from langchain_openai import ChatOpenAI

        model = kwargs.pop("model", os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
        return ChatOpenAI(model=model, temperature=temperature, **kwargs)

    raise ValueError(f"Unknown LLM provider: {provider!r} (expected 'fake', 'openai', or 'anthropic')")
