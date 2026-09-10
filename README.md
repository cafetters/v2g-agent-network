# V2G Agent Network

A minimal multi-agent simulation in which three AI agents from different
organizations negotiate where to pre-position idle electric bus batteries
(vehicle-to-grid) near vulnerable Boston neighborhoods ahead of a storm.

## What it does

- **EmergencyAgent** (city emergency management) reads the storm forecast and
  neighborhood data, and proposes priority zones ranked by social vulnerability
  x outage risk.
- **FleetAgent** (transit authority) assigns specific buses given state of
  charge and route status, and pushes back if a proposal would strand service
  or use low-charge buses.
- **UtilityAgent** (grid operator) checks each staging site against its grid
  tie-in capacity and rejects allocations that exceed it, stating a per-site
  bus limit.

The orchestrator runs up to 4 negotiation rounds, printing a round-by-round
trace, and stops when the utility approves. The synthetic data is designed so
at least one rejection happens (East Boston is top priority but its 100 kW
tie-in fits only one 60 kW bus). The final plan is written to
`output/staging_plan.json`.

## How to run

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install anthropic python-dotenv
# put ANTHROPIC_API_KEY=sk-ant-... in .env
python orchestrator.py
```

All agent calls use `claude-sonnet-4-6` via the Anthropic Messages API with
forced tool use, so every decision comes back as structured JSON.

## Architecture (five lines)

1. `data/` holds synthetic JSON: neighborhoods, fleet, and one storm forecast.
2. Each agent in `agents/` is a class with a role system prompt and one decision tool; `tool_choice` forces a structured response.
3. `orchestrator.py` loops: Emergency proposes -> Fleet allocates -> Utility validates.
4. Rejections are serialized and fed back into the next round's prompts.
5. On approval (or round limit) the orchestrator computes kWh and coverage in plain Python and writes `output/staging_plan.json`.

## Known limitations

- Agents are stateless between rounds; feedback is passed as text, not conversation history.
- The utility's capacity arithmetic is done by the model, not verified in code (a real system would recheck deterministically). The orchestrator does deterministically drop duplicate bus assignments, since the models occasionally double-assign a bus.
- No travel time, charging logistics, weather uncertainty, or cost modeling; data is synthetic and small.
- Convergence within 4 rounds is likely but not guaranteed; on failure the last (unapproved) allocation is written with a warning.
