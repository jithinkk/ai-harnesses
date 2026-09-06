"""A scripted, deterministic `Model` used to drive Strands Agents SDK offline.

Strands' `Model.stream()` is an async generator of low-level streaming events
(`messageStart` / `contentBlockStart` / `contentBlockDelta` / `contentBlockStop` /
`messageStop`), not a single return value -- the most different model interface of the
three non-Dapr frameworks in this repo. `PersistentFakeModel` hides that plumbing behind
the same persistent-`responder` shape `shared/llm/fake.py`'s `FakeChatModel` and the
other harnesses' fakes use: `responder(messages)` returns a list of content blocks
(`{"text": ...}` or `{"toolUse": {...}}`), and this class turns that into the correctly
sequenced event stream itself.
"""

from __future__ import annotations

import json
from typing import Any, Callable

from strands.models.model import Model
from strands.types.content import Message

Responder = Callable[[list[Message]], list[dict[str, Any]]]


class PersistentFakeModel(Model):
    """Deterministic stand-in for a real `Model` (Bedrock/Anthropic/OpenAI/...)."""

    def __init__(self, responder: Responder) -> None:
        self._responder = responder

    def get_config(self) -> Any:
        return {}

    def update_config(self, **model_config: Any) -> None:
        pass

    async def structured_output(self, output_model, prompt, system_prompt=None, **kwargs):
        # Not exercised by this harness.
        raise NotImplementedError("PersistentFakeModel does not support structured_output")
        yield  # pragma: no cover -- makes this an async generator to satisfy Model's signature

    async def stream(self, messages, tool_specs=None, system_prompt=None, **kwargs):
        blocks = self._responder(messages)

        yield {"messageStart": {"role": "assistant"}}
        for index, block in enumerate(blocks):
            if "text" in block:
                yield {"contentBlockStart": {"contentBlockIndex": index, "start": {}}}
                yield {"contentBlockDelta": {"contentBlockIndex": index, "delta": {"text": block["text"]}}}
            elif "toolUse" in block:
                tool_use = block["toolUse"]
                yield {
                    "contentBlockStart": {
                        "contentBlockIndex": index,
                        "start": {"toolUse": {"toolUseId": tool_use["toolUseId"], "name": tool_use["name"]}},
                    }
                }
                yield {
                    "contentBlockDelta": {
                        "contentBlockIndex": index,
                        "delta": {"toolUse": {"input": json.dumps(tool_use["input"])}},
                    }
                }
            yield {"contentBlockStop": {"contentBlockIndex": index}}

        stop_reason = "tool_use" if any("toolUse" in b for b in blocks) else "end_turn"
        yield {"messageStop": {"stopReason": stop_reason}}
