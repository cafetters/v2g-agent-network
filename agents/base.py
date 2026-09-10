"""Shared base: every agent is a thin wrapper around one forced tool-use call."""
import os

import anthropic
from dotenv import load_dotenv

load_dotenv()

MODEL = "claude-sonnet-4-6"


class BaseAgent:
    name = "BaseAgent"
    system = ""

    def __init__(self):
        self.client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    def call_tool(self, user_content: str, tool: dict) -> dict:
        """Send one message, force the agent to answer via its decision tool."""
        response = self.client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=self.system,
            tools=[tool],
            tool_choice={"type": "tool", "name": tool["name"]},
            messages=[{"role": "user", "content": user_content}],
        )
        return next(b for b in response.content if b.type == "tool_use").input
