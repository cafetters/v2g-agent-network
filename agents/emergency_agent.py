"""EmergencyAgent: city emergency management. Ranks neighborhoods for staging."""
import json

from agents.base import BaseAgent

PROPOSE_TOOL = {
    "name": "propose_priority_zones",
    "description": "Propose neighborhoods to stage bus batteries in, ranked by need.",
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {
            "priority_zones": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "neighborhood": {"type": "string"},
                        "priority_score": {"type": "number"},
                        "reason": {"type": "string"},
                    },
                    "required": ["neighborhood", "priority_score", "reason"],
                    "additionalProperties": False,
                },
            },
            "summary": {"type": "string", "description": "One-line rationale."},
        },
        "required": ["priority_zones", "summary"],
        "additionalProperties": False,
    },
}


class EmergencyAgent(BaseAgent):
    name = "EmergencyAgent"
    system = (
        "You are the City of Boston emergency management agent preparing for a storm. "
        "Rank neighborhoods for mobile battery staging by priority_score = "
        "social_vulnerability_index x outage risk, weighing critical residents "
        "(home dialysis, oxygen-dependent). Propose the top 4-5 zones only. "
        "The highest-priority zones need enough staged power to support their "
        "critical residents. If reviewers raise objections, adjust your ranking "
        "only where their reasons genuinely warrant it."
    )

    def propose(self, forecast: dict, neighborhoods: list, feedback: str | None) -> dict:
        content = (
            f"Storm forecast:\n{json.dumps(forecast)}\n\n"
            f"Neighborhoods:\n{json.dumps(neighborhoods)}\n\n"
            + (f"Feedback from last round:\n{feedback}\n\n" if feedback else "")
            + "Propose priority staging zones."
        )
        return self.call_tool(content, PROPOSE_TOOL)
