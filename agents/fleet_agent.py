"""FleetAgent: transit operator. Assigns buses to zones, protects service."""
import json

from agents.base import BaseAgent

ALLOCATE_TOOL = {
    "name": "propose_allocation",
    "description": "Assign specific buses to staging neighborhoods.",
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {
            "assignments": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "bus_id": {"type": "string"},
                        "neighborhood": {"type": "string"},
                        "reason": {"type": "string"},
                    },
                    "required": ["bus_id", "neighborhood", "reason"],
                    "additionalProperties": False,
                },
            },
            "objections": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Pushback on the priority proposal, if any.",
            },
            "summary": {"type": "string", "description": "One-line rationale."},
        },
        "required": ["assignments", "objections", "summary"],
        "additionalProperties": False,
    },
}


class FleetAgent(BaseAgent):
    name = "FleetAgent"
    system = (
        "You are the transit authority fleet agent. Assign electric buses to the "
        "proposed staging zones. Hard rules: never assign buses that are "
        "in_service or in maintenance (object instead if the proposal would "
        "strand service), and never assign buses below 50% state of charge - "
        "object if asked to. Prefer high-charge idle buses and nearby depots. "
        "Send at least 2 buses to the top-priority zone if charge allows, since "
        "it has the most critical residents. If the utility gave you capacity "
        "limits in feedback, respect them exactly. Assign each bus to at most "
        "ONE neighborhood, use only bus IDs that appear in the fleet data, and "
        "never emit placeholder or standby entries. If eligible buses run out, "
        "leave the lowest-priority zones unserved and say so in objections."
    )

    def __init__(self, fleet: list):
        super().__init__(f"Fleet status:\n{json.dumps(fleet)}")

    def allocate(self, context: dict, feedback: str | None) -> dict:
        content = (
            f"Staging context:\n{json.dumps(context)}\n\n"
            + (f"Feedback from last round:\n{feedback}\n\n" if feedback else "")
            + "Propose a bus-to-neighborhood allocation."
        )
        return self.call_tool(content, ALLOCATE_TOOL)
