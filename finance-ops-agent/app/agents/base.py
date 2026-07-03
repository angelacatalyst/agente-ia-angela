"""Base agent class — shared logic for all 8 Finance Ops modules."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from typing import Any, AsyncIterator

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import BaseTool

from app.core.config import get_settings
from app.core.logging import get_logger
from app.prompts.modules import MODULE_PROMPTS

logger = get_logger(__name__)
settings = get_settings()


class FinanceAgentBase(ABC):
    """
    Base class for all Finance Ops sub-agents.

    Each sub-agent:
      - Has a module name matching MODULE_PROMPTS keys
      - Holds its own tool list
      - Exposes an async `run()` method (full response)
      - Exposes an async `stream()` method (token-by-token SSE)
    """

    module: str  # Must be set in each subclass

    def __init__(self, extra_tools: list[BaseTool] | None = None) -> None:
        self._settings = settings
        self._llm = ChatAnthropic(
            model=settings.anthropic_model,
            max_tokens=settings.anthropic_max_tokens,
            api_key=settings.anthropic_api_key,
            streaming=True,
        )
        self._tools: list[BaseTool] = self._default_tools()
        if extra_tools:
            self._tools.extend(extra_tools)

        self._system_prompt = MODULE_PROMPTS.get(self.module, MODULE_PROMPTS["orchestrator"])
        self._llm_with_tools = self._llm.bind_tools(self._tools) if self._tools else self._llm

    @abstractmethod
    def _default_tools(self) -> list[BaseTool]:
        """Return the default tools for this agent module."""
        ...

    def _build_messages(
        self,
        user_input: str,
        history: list[BaseMessage] | None = None,
        context: dict[str, Any] | None = None,
    ) -> list[BaseMessage]:
        messages: list[BaseMessage] = [SystemMessage(content=self._system_prompt)]

        if context:
            ctx_text = "\n".join(f"**{k}**: {v}" for k, v in context.items())
            messages.append(SystemMessage(content=f"## Session Context\n{ctx_text}"))

        if history:
            messages.extend(history)

        messages.append(HumanMessage(content=user_input))
        return messages

    async def run(
        self,
        user_input: str,
        history: list[BaseMessage] | None = None,
        context: dict[str, Any] | None = None,
        conversation_id: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        """Run the agent and return a full response dict."""
        messages = self._build_messages(user_input, history, context)
        tool_calls_made: list[str] = []

        # Agentic loop: handle tool calls
        current_messages = list(messages)
        max_iterations = 5

        for iteration in range(max_iterations):
            response: AIMessage = await self._llm_with_tools.ainvoke(current_messages)  # type: ignore
            current_messages.append(response)

            if not response.tool_calls:
                # Final response — no more tool calls
                break

            # Execute tool calls
            for tc in response.tool_calls:
                tool_name = tc["name"]
                tool_args = tc["args"]
                tool_calls_made.append(tool_name)

                logger.info(
                    "Agent tool call",
                    module=self.module,
                    tool=tool_name,
                    iteration=iteration,
                )

                tool_result = await self._call_tool(tool_name, tool_args)
                from langchain_core.messages import ToolMessage
                current_messages.append(
                    ToolMessage(
                        content=str(tool_result),
                        tool_call_id=tc["id"],
                        name=tool_name,
                    )
                )

        final = current_messages[-1]
        content = final.content if isinstance(final.content, str) else str(final.content)

        return {
            "content": content,
            "tool_calls_made": tool_calls_made,
            "conversation_id": str(conversation_id or uuid.uuid4()),
            "module": self.module,
        }

    async def stream(
        self,
        user_input: str,
        history: list[BaseMessage] | None = None,
        context: dict[str, Any] | None = None,
    ) -> AsyncIterator[str]:
        """Stream tokens from the agent. Yields text chunks."""
        messages = self._build_messages(user_input, history, context)

        async for chunk in self._llm_with_tools.astream(messages):
            if hasattr(chunk, "content") and isinstance(chunk.content, str):
                yield chunk.content
            elif hasattr(chunk, "content") and isinstance(chunk.content, list):
                for block in chunk.content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        yield block.get("text", "")

    async def _call_tool(self, tool_name: str, args: dict[str, Any]) -> Any:
        """Look up and invoke a tool by name."""
        for tool in self._tools:
            if tool.name == tool_name:
                try:
                    if hasattr(tool, "acoroutine"):
                        return await tool.acoroutine(**args)
                    return await tool.ainvoke(args)
                except Exception as exc:
                    logger.error("Tool call failed", tool=tool_name, error=str(exc))
                    return f"Tool error: {exc}"
        return f"Tool '{tool_name}' not found"
