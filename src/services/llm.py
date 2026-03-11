"""LLM service: streaming chat completions via OpenAI GPT-4o with tool calling."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from openai import AsyncOpenAI, NOT_GIVEN

from src.config import APIConfig

if TYPE_CHECKING:
    from src.services.tools import ToolExecutor

logger = logging.getLogger(__name__)

# Safety limit on tool-call round-trips to avoid infinite loops.
_MAX_TOOL_ITERATIONS = 3


class LLMService:
    """Streams text responses from the OpenAI chat completions API.

    Supports OpenAI function calling (tool use). When the LLM emits a tool
    call instead of text, this service executes the tool, feeds the result
    back, and continues streaming -- all transparently to the caller.

    Cancellation-safe: ``asyncio.CancelledError`` propagates through the
    ``async for`` loop and tool execution, closing HTTP connections.

    Usage::

        llm = LLMService(client, tools=TOOL_DEFINITIONS, tool_executor=executor)
        async for token in llm.stream_response(messages):
            print(token, end="")
    """

    def __init__(
        self,
        client: AsyncOpenAI,
        config: APIConfig | None = None,
        tools: list[dict] | None = None,
        tool_executor: ToolExecutor | None = None,
    ) -> None:
        self._client = client
        self._config = config or APIConfig()
        self._tools = tools
        self._tool_executor = tool_executor

    async def stream_response(
        self,
        messages: list[dict],
    ) -> AsyncIterator[str]:
        """Stream text deltas from the LLM, handling tool calls transparently.

        If the LLM decides to call a tool, this method:
        1. Accumulates the streamed tool call arguments.
        2. Executes the tool via the ToolExecutor.
        3. Appends the tool result to messages and re-calls the API.
        4. Yields text deltas from the follow-up response.

        Args:
            messages: Conversation history in OpenAI message format.

        Yields:
            Text delta strings as they arrive from the API.
        """
        current_messages = list(messages)

        for iteration in range(_MAX_TOOL_ITERATIONS):
            stream = await self._client.chat.completions.create(
                model=self._config.llm_model,
                messages=current_messages,
                stream=True,
                tools=self._tools if self._tools else NOT_GIVEN,
            )

            # Accumulators for tool calls streamed in chunks.
            tool_calls_acc: dict[int, dict] = {}
            has_tool_calls = False

            async for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta

                # Yield text content immediately to the caller.
                if delta.content:
                    yield delta.content

                # Accumulate tool call fragments.
                if delta.tool_calls:
                    has_tool_calls = True
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in tool_calls_acc:
                            tool_calls_acc[idx] = {
                                "id": "",
                                "name": "",
                                "arguments": "",
                            }
                        if tc.id:
                            tool_calls_acc[idx]["id"] = tc.id
                        if tc.function and tc.function.name:
                            tool_calls_acc[idx]["name"] = tc.function.name
                        if tc.function and tc.function.arguments:
                            tool_calls_acc[idx]["arguments"] += tc.function.arguments

            # No tool calls -- normal completion, we're done.
            if not has_tool_calls:
                return

            # Execute tool calls and feed results back.
            logger.info(
                "LLM requested %d tool call(s) on iteration %d",
                len(tool_calls_acc),
                iteration + 1,
            )

            # Build the assistant message with tool_calls for the API.
            assistant_tool_calls = [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": tc["arguments"],
                    },
                }
                for tc in tool_calls_acc.values()
            ]
            current_messages.append({
                "role": "assistant",
                "tool_calls": assistant_tool_calls,
            })

            # Execute each tool and append the result.
            for tc in tool_calls_acc.values():
                if self._tool_executor is None:
                    result = '{"error": "No tool executor configured"}'
                else:
                    logger.info("Executing tool: %s(%s)", tc["name"], tc["arguments"][:100])
                    result = await self._tool_executor.execute(
                        tc["name"], tc["arguments"],
                    )
                current_messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": result,
                })

            # Loop continues: next iteration streams the LLM's text response
            # incorporating the tool results.

        logger.warning("Hit max tool iterations (%d), stopping", _MAX_TOOL_ITERATIONS)
