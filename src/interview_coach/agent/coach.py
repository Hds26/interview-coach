"""Agent loop: prompt, local tools, then a final answer. Default model is offline."""

from __future__ import annotations

from interview_coach.agent.llm import LLM
from interview_coach.agent.prompts import SYSTEM_PROMPT
from interview_coach.agent.tools import ToolRegistry, tool_specs


class CoachAgent:
    def __init__(self, llm: LLM, tools: ToolRegistry) -> None:
        self.llm = llm
        self.tools = tools

    def ask(self, user_text: str) -> str:
        messages: list[dict] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_text},
        ]
        for _ in range(3):
            result = self.llm.complete(messages, tools=tool_specs())
            if not result.tool_calls:
                text = result.content.strip()
                return text or "No advice produced."
            messages.append(
                {
                    "role": "assistant",
                    "content": result.content,
                    "tool_calls": [call.as_dict() for call in result.tool_calls],
                }
            )
            for call in result.tool_calls:
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "name": call.name,
                        "content": self.tools.dispatch(call.name, call.arguments),
                    }
                )
        return "I could not finish a recommendation from the local tools."
