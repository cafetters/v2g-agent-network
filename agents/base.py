"""Shared base: every agent is a thin wrapper around one forced tool-use call."""
import os

import anthropic
from dotenv import load_dotenv

load_dotenv()

MODEL = "claude-sonnet-4-6"


class BaseAgent:
    name = "BaseAgent"
    system = ""
    # process-wide token accumulator; the orchestrator snapshots it per run
    TOKENS = {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}

    def __init__(self, static_context: str = ""):
        self.client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        self.static_context = static_context

    def call_tool(self, user_content: str, tool: dict) -> dict:
        """One forced tool-use call. The static prefix is cached across calls.

        Cache prefix = tools + system prompt + static scenario data (marked
        with cache_control); everything that varies per round stays in the
        user message so the prefix bytes never change within a batch.
        """
        system_blocks = [{"type": "text", "text": self.system}]
        if self.static_context:
            system_blocks.append({"type": "text", "text": self.static_context})
        system_blocks[-1]["cache_control"] = {"type": "ephemeral"}
        response = self.client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=system_blocks,
            tools=[tool],
            tool_choice={"type": "tool", "name": tool["name"]},
            messages=[{"role": "user", "content": user_content}],
        )
        usage = response.usage
        BaseAgent.TOKENS["input"] += usage.input_tokens
        BaseAgent.TOKENS["output"] += usage.output_tokens
        BaseAgent.TOKENS["cache_read"] += usage.cache_read_input_tokens or 0
        BaseAgent.TOKENS["cache_write"] += usage.cache_creation_input_tokens or 0
        return next(b for b in response.content if b.type == "tool_use").input
