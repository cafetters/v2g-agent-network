"""UtilityAgent: grid operator. Checks staging sites against tie-in capacity."""
import json

from agents.base import BaseAgent

VALIDATE_TOOL = {
    "name": "validate_plan",
    "description": "Approve or reject the proposed staging allocation.",
    "input_schema": {
        "type": "object",
        "properties": {
            "approved": {"type": "boolean"},
            "rejections": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "neighborhood": {"type": "string"},
                        "reason": {"type": "string"},
                        "max_buses": {
                            "type": "integer",
                            "description": "Most buses this tie-in can accept.",
                        },
                    },
                    "required": ["neighborhood", "reason", "max_buses"],
                },
            },
            "summary": {"type": "string", "description": "One-line rationale."},
        },
        "required": ["approved", "rejections", "summary"],
    },
}


class UtilityAgent(BaseAgent):
    name = "UtilityAgent"
    system = (
        "You are the electric utility interconnection agent. Each bus exports at "
        "its v2g_export_kw rating. For every neighborhood in the allocation, sum "
        "the export kW of assigned buses and compare it to the neighborhood's "
        "grid_tie_in_kw. If the sum exceeds capacity, reject that neighborhood "
        "and state max_buses = floor(grid_tie_in_kw / 60). Approve only when "
        "every staging site fits its tie-in capacity. Do the arithmetic "
        "carefully; do not approve out of politeness."
    )

    def validate(self, allocation: dict, neighborhoods: list, fleet: list) -> dict:
        content = (
            f"Proposed allocation:\n{json.dumps(allocation)}\n\n"
            f"Neighborhood grid tie-in capacities:\n{json.dumps(neighborhoods)}\n\n"
            f"Bus export ratings:\n{json.dumps(fleet)}\n\n"
            "Validate the plan against grid tie-in capacity."
        )
        return self.call_tool(content, VALIDATE_TOOL)
