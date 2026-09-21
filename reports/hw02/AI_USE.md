# AI_USE.md — DATA-260 HW2

## 1. What I used an AI assistant for, and what I did myself

**Used AI for:**
- nitial scaffolding for the FastAPI backend (code/backend/main.py) and the list/search UI (index.html / script.js) for Parts 1–2, which I then modified and extended
A first draft of the LangGraph refactor (AgentState, planner_node, reviewer_node, supervisor_node, router_logic) for Part 3, and a first draft of the Pydantic schema + retry logic for Part 4 — both of which I rewrote significantly to get working correctly
A starting point for the three experiment runner scripts (run_schema_experiment.py, run_ceiling_experiment.py, run_adversarial_experiment.py) and the verify_hw02.py smoke-test script
A rough draft of the initial adversarial input case, which I revised

**Did myself:**
- Installed and ran everything locally (Ollama, qwen2.5:3b, pip installs, uvicorn) and fixed all environment issues as they came up (missing pip/venv activation, missing langgraph package, a filename typo in schema_input.json)
Debugged and rewrote significant portions of the AI-scaffolded code to get it actually working — including fixing logic errors in the LangGraph nodes and correcting the experiment runner scripts
Ran all 75 real experiment trials (30 + 40 + 5) against my actual local model on my own machine and captured the real console output
Verified every stage worked by actually opening the app in the browser, clicking through search/add/update/delete, and watching the terminal logs — not just trusting that the code "looked right"
Decided the deployment recommendation (turn_ceiling=10) based on my own reading of the completion-rate vs. latency trade-off in the data
Made the final call on repo structure and which files to keep from HW1

## 2. An AI-produced output that was wrong, and how I caught it

The initial AI-drafted `planner_node` implementation (part of the LangGraph
refactor I significantly rewrote for Part 3) had a real bug: when the
Reviewer flagged an issue and the graph routed back to the Planner for a
retry, the Planner's return value did not clear the previous
`reviewer_feedback` from state. Because the router (`router_logic`) checks
`reviewer_feedback` to decide whether to send the proposal to the Reviewer
again, the *stale* feedback from the prior round was still sitting in
state — so the router treated it as still valid, decided "issues were
already flagged, go straight back to the Planner," and skipped the
Reviewer node entirely on every subsequent retry. The self-correction loop
was silently degrading into a Planner-only loop that never got reviewed a
second time.

## 3. How I detected the problem / verified the result

I did not catch this by reading the code — it looked correct on
inspection, which is exactly why I didn't just trust the AI-scaffolded
version as-is. I wrote a small test harness myself that mocked
`ModelClient.complete()` with canned Planner/Reviewer responses and logged
which node was called on each graph step (`call_log`). Running the
"reviewer always flags an issue" scenario, the expected call sequence was
`PLANNER, REVIEWER, PLANNER, REVIEWER, ...` (alternating), but the actual
log showed `PLANNER, REVIEWER, PLANNER, PLANNER, PLANNER, ...` — the
Reviewer only ran once. That mismatch between expected and actual call
sequence is what surfaced the bug; it would not have been visible from a
single manual run with the real (non-deterministic) local model, since a
single run's output looking "fine" doesn't tell you whether the loop
mechanism itself is correct.

## 4. What I changed, and why it works now

I rewrote `planner_node` to explicitly return `"reviewer_feedback": {}`
alongside the new `planner_proposal` every time it runs, clearing out any
stale feedback from a previous round. This forces the router to see "no
reviewer feedback yet" after every fresh Planner draft, correctly routing
to the Reviewer again instead of reusing an old verdict. After the fix, I
reran the same mocked test I had written and confirmed the call sequence
strictly alternates `PLANNER, REVIEWER, PLANNER, REVIEWER, ...` for as
many retries as the turn ceiling allows, and that the graph still
terminates cleanly (via the ceiling) even when the Reviewer is forced to
always report issues — confirming both the fix and the safety net work
together.

## Takeaways

- A graph that "runs without crashing" and even produces a plausible final
  answer is not the same as a graph whose *routing logic* is correct — the
  planner-only-loop bug never raised an exception; it just silently did
  less reviewing than intended.
- Testing the routing logic with a mocked model (deterministic, fast,
  free) caught a structural bug that would have been much harder to
  isolate from real-model runs alone, since the real model's
  non-determinism (see Part 4.3: 0 runs recovered after a retry) could
  easily be misattributed to "the model is just bad at this" rather than
  "the loop isn't actually re-reviewing."
- The 8GB RAM hardware constraint is real: the schema experiment (30
  sequential runs) ran roughly 10x slower than a fresh calibration run
  taken right afterward, suggesting sustained load causes real
  performance degradation on this machine that a short test wouldn't
  reveal — worth planning around for any future batch experiments.