"""LLM-driven agent loop using Claude tool-use.

This replaces the heuristic AgentOrchestrator for the new /agent/stream
endpoint while the old orchestrator remains available at /generate.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, AsyncIterator, Callable

from app.core.config import settings
from app.services.llm_service import LLMService, ToolCall
from app.tools.base import ToolContext, ToolRegistry, ToolResult

logger = logging.getLogger(__name__)

# Keywords that trigger a human approval gate before execution.
RISKY_KEYWORDS = {
    "drop table", "drop database", "truncate", "delete from",
    "rm -rf", "rm -r", "rmdir", "git push", "force",
    "migration", "alter table", "shutdown", "reboot",
}


# ------------------------------------------------------------------
# Stream event types
# ------------------------------------------------------------------
@dataclass
class StreamEvent:
    type: str
    data: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps({"type": self.type, "data": self.data}, ensure_ascii=False)


@dataclass
class AgentRunResult:
    run_id: str
    status: str  # "completed" | "failed" | "approval_pending"
    final_text: str = ""
    tool_calls_count: int = 0
    steps: int = 0


class AgentRunner:
    """LLM-driven agentic loop with tool-use."""

    def __init__(
        self,
        llm: LLMService,
        tool_registry: ToolRegistry,
    ):
        self.llm = llm
        self.tools = tool_registry

    # ------------------------------------------------------------------
    # Main entry: streaming
    # ------------------------------------------------------------------
    async def run_stream(
        self,
        session_id: str,
        query: str,
        workspace: str,
        current_file: str | None = None,
        rag_context: str | None = None,
        memory_context: str | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """Execute an agent run, yielding ``StreamEvent`` objects."""

        run_id = str(uuid.uuid4())
        system_prompt = self._build_system_prompt(
            workspace=workspace,
            current_file=current_file,
            rag_context=rag_context,
            memory_context=memory_context,
        )

        messages: list[dict[str, Any]] = [{"role": "user", "content": query}]

        tool_context = ToolContext(
            session_id=session_id,
            run_id=run_id,
            workspace=workspace,
        )

        yield StreamEvent("status", {"message": "Agent started", "step": 0, "run_id": run_id})

        total_tool_calls = 0

        for step in range(1, settings.deep_agent_max_steps + 1):
            yield StreamEvent("status", {"message": f"Thinking (step {step})…", "step": step})

            # Accumulate the assistant turn
            accumulated_text = ""
            tool_calls: list[ToolCall] = []
            content_blocks: list[dict[str, Any]] = []

            try:
                async for chunk in self.llm.chat_with_tools_stream(
                    messages=messages,
                    system_prompt=system_prompt,
                    tools=self.tools.claude_tool_definitions(),
                ):
                    if chunk.type == "text_delta" and chunk.text:
                        accumulated_text += chunk.text
                        yield StreamEvent("text_delta", {"text": chunk.text})
                    elif chunk.type == "tool_use" and chunk.tool_call:
                        tool_calls.append(chunk.tool_call)
                        yield StreamEvent(
                            "tool_call",
                            {
                                "tool": chunk.tool_call.tool_name,
                                "input": chunk.tool_call.tool_input,
                                "id": chunk.tool_call.tool_use_id,
                            },
                        )
            except Exception as e:
                logger.exception("LLM call failed at step %d", step)
                yield StreamEvent("error", {"message": f"LLM error: {e}"})
                yield StreamEvent("done", {"run_id": run_id, "status": "failed"})
                return

            # Build the assistant message for OpenAI format
            if not tool_calls:
                # Pure text response – just append and finish
                if accumulated_text:
                    messages.append({"role": "assistant", "content": accumulated_text})
                yield StreamEvent("done", {"run_id": run_id, "status": "completed"})
                return

            # Assistant message with tool_calls (OpenAI format)
            assistant_msg: dict[str, Any] = {
                "role": "assistant",
                "content": accumulated_text or None,
                "tool_calls": [
                    {
                        "id": tc.tool_use_id,
                        "type": "function",
                        "function": {
                            "name": tc.tool_name,
                            "arguments": json.dumps(tc.tool_input, ensure_ascii=False),
                        },
                    }
                    for tc in tool_calls
                ],
            }
            messages.append(assistant_msg)

            # Execute each tool call and append results as "tool" role messages
            for tc in tool_calls:
                total_tool_calls += 1

                # Check for risky operations
                if self._needs_approval(tc):
                    yield StreamEvent(
                        "approval_required",
                        {
                            "run_id": run_id,
                            "tool": tc.tool_name,
                            "input": tc.tool_input,
                            "reason": f"Risky operation detected in {tc.tool_name}",
                        },
                    )
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.tool_use_id,
                        "content": "Operation rejected: requires human approval.",
                    })
                    continue

                tool = self.tools.get(tc.tool_name)
                if not tool:
                    result = ToolResult(False, f"Unknown tool: {tc.tool_name}")
                else:
                    t0 = perf_counter()
                    try:
                        result = await tool.execute(tc.tool_input, tool_context)
                    except Exception as e:
                        logger.exception("Tool %s execution error", tc.tool_name)
                        result = ToolResult(False, f"Tool execution error: {e}")
                    elapsed_ms = int((perf_counter() - t0) * 1000)
                    logger.info(
                        "Tool %s completed in %dms success=%s",
                        tc.tool_name, elapsed_ms, result.success,
                    )

                yield StreamEvent(
                    "tool_result",
                    {
                        "id": tc.tool_use_id,
                        "tool": tc.tool_name,
                        "success": result.success,
                        "output": result.output[:4000],
                    },
                )

                # Emit diff_preview for write/edit tools
                if tc.tool_name in ("write_file", "edit_file") and result.success:
                    yield StreamEvent(
                        "diff_preview",
                        {
                            "path": tc.tool_input.get("path", ""),
                            "tool": tc.tool_name,
                            "detail": result.output[:2000],
                        },
                    )

                # OpenAI format: each tool result is a separate "tool" role message
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.tool_use_id,
                    "content": result.output[:4000],
                })

        # Exhausted max steps
        yield StreamEvent("done", {"run_id": run_id, "status": "max_steps_reached"})

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _build_system_prompt(
        self,
        workspace: str,
        current_file: str | None,
        rag_context: str | None,
        memory_context: str | None,
    ) -> str:
        parts = [
            "You are an expert AI coding assistant. You help users with software engineering tasks "
            "by reading, writing, and editing files, running shell commands, and using git.\n",
            "## Guidelines\n"
            "- Read files before editing them to understand existing code.\n"
            "- Make minimal, targeted changes. Don't over-engineer.\n"
            "- Use edit_file for small changes, write_file only for new files or full rewrites.\n"
            "- Run tests after making changes when applicable.\n"
            "- Explain what you're doing briefly before taking action.\n"
            "- If you're unsure about something, search the codebase first.\n",
            f"## Workspace\nYou are working in: {workspace}\n",
        ]

        if current_file:
            parts.append(f"## Current File\nThe user is viewing: {current_file}\n")

        if rag_context:
            parts.append(f"## Codebase Context\n{rag_context}\n")

        if memory_context:
            parts.append(f"## Conversation History Summary\n{memory_context}\n")

        return "\n".join(parts)

    @staticmethod
    def _needs_approval(tc: ToolCall) -> bool:
        """Check if a tool call contains risky operations."""
        text_to_check = json.dumps(tc.tool_input, ensure_ascii=False).lower()
        return any(kw in text_to_check for kw in RISKY_KEYWORDS)
