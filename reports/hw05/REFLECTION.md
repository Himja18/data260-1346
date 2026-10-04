# HW5 Part 5 Reflection: run `bb352ae8` (scenario S5, stop reason `max_steps`)

**Prompt:** for lines L-005, L-012, L-020 and L-033, get the incident stats and then the full details of each line's most recent Delay incident. The harness used `qwen2.5:3b` with `max_steps = 3`.

**Step 1.** The harness sent the system prompt, the user prompt and the three tool schemas. The model answered with four parallel `search_incidents` calls, one per line, each with `category: "Delay", limit: 1`. Every call passed through `execute_tool`; the safety rule allowed them because each was scoped by `line_code` and `category`. All four returned `ok: true` with one incident (INC-005005, INC-004848, INC-004750, INC-004607). The turn counter moved to 2.

**Step 2.** The model requested four `get_incident` calls but added an extra `line_code` field. Input validation rejected each one before the database was touched, returning `ok: false` with "unknown field(s) ['line_code']; allowed: ['incident_code']". Nothing crashed; the errors were fed back as tool messages.

**Step 3.** Using those error messages, the model fixed its own mistake and resent the four `get_incident` calls with only `incident_code`. All four succeeded and returned line name and mode.

**Why it stopped.** The loop had used its third and final step, so the harness ended the run with `stop_reason: "max_steps"` after 3 steps and 12 tool calls (60.25 s), even though the model now had the details it needed. The ceiling counts model turns, not tool calls, which is why 12 calls fit in 3 steps.

**What I learned.** Clear envelope errors let a small model self-correct within one turn. The run also exposed a gap: the model never called `incident_stats`, so part of the request was skipped. A step limit of 4–5, or a check that every requested sub-task was attempted, would let this run complete correctly.
