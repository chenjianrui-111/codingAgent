"""LLM client service wrapping ZhiPu AI (OpenAI-compatible) with streaming + tool-use."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from openai import AsyncOpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class ToolCall:
    tool_name: str
    tool_input: dict[str, Any]
    tool_use_id: str


@dataclass
class LLMStreamChunk:
    """A single chunk emitted during an LLM streaming response."""

    type: str  # "text_delta" | "tool_use" | "message_stop" | "error"
    text: str | None = None
    tool_call: ToolCall | None = None


@dataclass
class LLMResponse:
    """Non-streaming aggregated response."""

    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_reason: str | None = None


def _convert_tools_to_openai(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert our tool definitions (Anthropic-style) to OpenAI function-calling format."""
    result = []
    for t in tools:
        result.append({
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
            },
        })
    return result


class LLMService:
    """Async wrapper around ZhiPu AI (OpenAI-compatible) for tool-use conversations."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
    ):
        self._api_key = api_key or settings.llm_api_key
        self._model = model or settings.llm_model
        self._base_url = base_url or settings.llm_base_url
        if not self._api_key:
            logger.warning("No LLM API key configured – LLM calls will fail")
        self.client = AsyncOpenAI(api_key=self._api_key, base_url=self._base_url)

    # ------------------------------------------------------------------
    # Streaming interface
    # ------------------------------------------------------------------
    async def chat_with_tools_stream(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str,
        tools: list[dict[str, Any]],
        max_tokens: int | None = None,
    ) -> AsyncIterator[LLMStreamChunk]:
        """Stream a ZhiPu response with tool-use support.

        Yields ``LLMStreamChunk`` instances as the model generates text
        and/or invokes tools.
        """
        max_tokens = max_tokens or settings.llm_max_tokens

        # Build the full messages list with system prompt
        full_messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            *messages,
        ]

        # Convert tools to OpenAI format
        openai_tools = _convert_tools_to_openai(tools) if tools else None

        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": full_messages,
            "max_tokens": max_tokens,
            "stream": True,
        }
        if openai_tools:
            kwargs["tools"] = openai_tools
            kwargs["tool_choice"] = "auto"

        stream = await self.client.chat.completions.create(**kwargs)

        # Track partial tool calls across chunks
        # OpenAI streaming sends tool calls incrementally:
        #   - first chunk has function name + empty args
        #   - subsequent chunks append to args string
        partial_tool_calls: dict[int, dict[str, str]] = {}

        async for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            finish_reason = chunk.choices[0].finish_reason if chunk.choices else None

            if delta:
                # Text content
                if delta.content:
                    yield LLMStreamChunk(type="text_delta", text=delta.content)

                # Tool calls (streamed incrementally)
                if delta.tool_calls:
                    for tc_delta in delta.tool_calls:
                        idx = tc_delta.index
                        if idx not in partial_tool_calls:
                            partial_tool_calls[idx] = {
                                "id": tc_delta.id or "",
                                "name": "",
                                "arguments": "",
                            }
                        entry = partial_tool_calls[idx]
                        if tc_delta.id:
                            entry["id"] = tc_delta.id
                        if tc_delta.function:
                            if tc_delta.function.name:
                                entry["name"] = tc_delta.function.name
                            if tc_delta.function.arguments:
                                entry["arguments"] += tc_delta.function.arguments

            # When the model finishes with tool_calls or stop
            if finish_reason == "tool_calls" or finish_reason == "stop":
                # Emit any completed tool calls
                for _idx in sorted(partial_tool_calls.keys()):
                    entry = partial_tool_calls[_idx]
                    try:
                        args = json.loads(entry["arguments"]) if entry["arguments"] else {}
                    except json.JSONDecodeError:
                        args = {"raw": entry["arguments"]}
                    yield LLMStreamChunk(
                        type="tool_use",
                        tool_call=ToolCall(
                            tool_name=entry["name"],
                            tool_input=args,
                            tool_use_id=entry["id"],
                        ),
                    )
                partial_tool_calls.clear()

                yield LLMStreamChunk(type="message_stop")

    # ------------------------------------------------------------------
    # Non-streaming convenience wrapper
    # ------------------------------------------------------------------
    async def chat_with_tools(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str,
        tools: list[dict[str, Any]],
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Non-streaming call that returns an aggregated ``LLMResponse``."""
        resp = LLMResponse()
        async for chunk in self.chat_with_tools_stream(
            messages=messages,
            system_prompt=system_prompt,
            tools=tools,
            max_tokens=max_tokens,
        ):
            if chunk.type == "text_delta" and chunk.text:
                resp.text += chunk.text
            elif chunk.type == "tool_use" and chunk.tool_call:
                resp.tool_calls.append(chunk.tool_call)
            elif chunk.type == "message_stop":
                resp.stop_reason = "end_turn"
        return resp
