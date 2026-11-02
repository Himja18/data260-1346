# HW8 - AI use (Himja Patel, s1346)

## 1. What I used an AI assistant for, and what I did myself
- **AI assistant (Claude):** read the HW8 handout and my HW1-HW7 repository and drafted the HW8 code on top of it:
  `hw08_config.py`, `kafka_common.py`, the Incident worker / Kafka client / FastAPI wrapper / `homework_demo.py`
  (Part 1), the Planner, Writer and Reviewer agents and `send_question.py` (Part 2), the shared agent loop with
  idempotency, commit-after-success and retries + dead-letter topic, the Part 3 runner (`run_hw08_part3.py`),
  `docker-compose.yml`, the Makefile targets, the offline tests, `verify_hw08.py`, `make_metrics_hw08.py` and a
  first draft of the report.
- **Myself:** ran everything on my MacBook: Docker Desktop, Kafka, the worker and API containers, Ollama with
  qwen2.5:3b; created the seven topics with the Kafka CLI (`make hw08-topics`); ran `homework_demo.py`; ran the
  Planner, Writer and Reviewer in separate terminals and sent questions; ran every Part 3 scenario before and after
  the fix; ran `make verify-hw08`; read each output, took all screenshots, checked the results against the handout,
  committed, tagged `hw8` and pushed.

## 2. AI-produced output that was wrong
The first Planner prompt gave the model a format example with placeholder steps
(`{"steps": ["step 1", "step 2", "step 3"]}`). On my first real run qwen2.5:3b copied it and sent the plan
`["Step 1", "Step 2", "Step 3", "Step 4"]` to `s1346_tasks`, so the Writer's draft began with "Step 1: ..." even
though the Reviewer approved it.

## 3. How I detected it
I read the Planner's `SENT -> s1346_tasks` line and the final answer of that first run, not just the status. The
pipeline itself worked (status approved, correlation_id preserved end to end), so only the content showed the
problem. The first entry in `raw/part2_journeys.json` (correlation_id 30f19a64-...) still shows it.

## 4. What changed and why it works now
The prompt now gives a real example plan for a different question; steps that are placeholders (`Step 1`, `...`) or
shorter than 12 characters are dropped; the model gets one retry with feedback; and a domain plan built from the
question is the last fallback. The second run (correlation_id e1fa1092-...) sent real steps ("Identify Line 22
trolley bus as the service affected", ...) and the final answer named the Breakdown category.
