# V2G Agent Network

## What this is

Three AI agents from different organizations — city emergency management, the
transit authority, and the electric utility — negotiate where to pre-position
idle electric bus batteries (vehicle-to-grid) near vulnerable Boston
neighborhoods ahead of a storm. Each agent is a role-prompted call to
`claude-sonnet-4-6` with forced tool use, and an orchestrator runs up to four
rounds of propose → allocate → validate until the utility approves a plan.

## What the first run taught me

The negotiation dynamics worked immediately — the utility correctly rejected a
120 kW allocation against East Boston's 100 kW tie-in in round one. What broke
was subtler: when the fleet agent ran out of eligible buses for the
lower-priority zones, it started **inventing bus IDs** (BEB-13 through BEB-21,
which don't exist) and **double-booking real buses** to multiple neighborhoods
rather than admitting it couldn't cover every zone. The plan never converged.

A prompt rule ("one zone per bus, real IDs only, leave zones unserved and say
so") mostly fixed the fleet agent — but on the next run the **utility agent
approved a plan containing a duplicate** it had caught and rejected in earlier
rounds. An LLM validator is a probabilistic check, and it missed the same bug
it had previously flagged.

The durable fix was a deterministic dedupe guard in the orchestrator that
drops repeat bus assignments before validation. The lesson: the constraint
moved from the model into the environment. Prompts shape behavior; code
guarantees invariants.

## How to run it

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install anthropic python-dotenv
# put ANTHROPIC_API_KEY=sk-ant-... in .env
python orchestrator.py
```

The round-by-round trace prints to the console; the final plan is written to
`output/staging_plan.json`.

## Architecture (five lines)

1. `data/` holds synthetic JSON: neighborhoods, fleet, and one storm forecast.
2. Each agent in `agents/` is a class with a role system prompt and one decision tool; `tool_choice` forces a structured response.
3. `orchestrator.py` loops: Emergency proposes -> Fleet allocates -> Utility validates.
4. Rejections are serialized and fed back into the next round's prompts, and a deterministic guard drops duplicate bus assignments.
5. On approval (or round limit) the orchestrator computes kWh and coverage in plain Python and writes `output/staging_plan.json`.

## Known limitations and what I'd build next

- Agents are stateless between rounds; feedback is passed as text, not conversation history. Next: give each agent a running conversation so it remembers its own commitments.
- The utility's capacity arithmetic is done by the model; only the duplicate check is enforced in code. Next: recheck kW-vs-tie-in deterministically and let the model handle judgment calls only.
- No travel time, charging logistics, weather uncertainty, or cost modeling; data is synthetic and small. Next: real MBTA depot locations and a proper dispatch cost function.
- Convergence within 4 rounds is likely but not guaranteed; on failure the last unapproved allocation is written with a warning.

---

Built with Claude Code in one evening; the scenario design and findings are mine.
