# DATA-260 HW8 - Himja Patel

**Repository:** https://github.com/Himja18/data260-1346  (collaborators Sbnikitha, supriyaselvanganesan have access - **[YOU] confirm**)

| SID4 | PORT_BASE | PREFIX | SEED | VERIFY_SEED | DOMAIN_ID |
|---|---|---|---|---|---|
| 1346 | 8446 | s1346 | 1346 | 261346 | 2 (Municipal Transit Incidents) |

**Hardware:** MacBook Pro 13" (Apple M2, 8 GB RAM), macOS · **Local model:** qwen2.5:3b via Ollama ·
**Kafka:** apache/kafka 3.8.0 (KRaft, single broker, Docker) · **Tagged commit (hw8):** `[YOU: git rev-parse hw8]`

> Formatting for the PDF: main headings 14 pt bold, subheadings 12 pt bold, body 11 pt. Every terminal
> screenshot must show "Himja Patel" (every log line carries it). Replace each **[SCREENSHOT]** box.

---

## Part 1 - Incident request/response over Kafka

### Topics and message schemas
Primary entity: **Incident** -> operations `CREATE_INCIDENT`, `GET_INCIDENT`, id field `incident_id`.

| Topic | Writer | Reader |
|---|---|---|
| `s1346_incident_requests` | client / FastAPI wrapper | incident worker (group `s1346_incident_worker`) |
| `s1346_incident_responses` | incident worker (topic named by `reply_to`) | client / FastAPI wrapper |

Request:
```json
{"correlation_id": "<uuid4 made once by the client>", "reply_to": "s1346_incident_responses",
 "operation": "CREATE_INCIDENT",
 "data": {"route_title": "Line 22 - Fillmore", "location": "Fillmore St & Geary Blvd",
          "category": "Breakdown", "passengers_affected": 37, "description": "optional"}}
```
Responses (the same `correlation_id` is echoed in every response, errors included):
```json
{"correlation_id": "...", "operation": "CREATE_INCIDENT", "success": true, "incident_id": "<uuid4>", "message": "Incident created"}
{"correlation_id": "...", "operation": "GET_INCIDENT", "success": true, "incident": {"incident_id": "...", "route_title": "...", "...": "..."}}
{"correlation_id": "...", "operation": "GET_INCIDENT", "success": false, "error": "Incident not found"}
{"correlation_id": "...", "operation": "DELETE_INCIDENT", "success": false, "error": "Unknown operation"}
```
Validation (worker, Pydantic, `extra="forbid"`): `route_title` 3-200 chars, `location` 2-200 chars, `category` one of
Delay / Breakdown / Accident / Service Change, `passengers_affected` integer 0-100000 (strict: no strings or
booleans), `description` optional <= 1000 chars. Missing, empty (also whitespace-only) and invalid values are rejected
with one clean `"Validation failed: ..."` message. Incidents are stored in a plain dict inside the worker.

### correlation_id flow
1. `homework_demo.py` (or the FastAPI wrapper, from `X-Correlation-ID` or a new uuid4) creates the id **once**.
2. The client sends it in the request and registers a waiter for that id **before** sending.
3. The worker reads it from the request and copies it unchanged into the response (and into error responses).
4. A background thread in the client reads `s1346_incident_responses` and wakes the waiter whose id matches;
   the demo then checks `response.correlation_id == sent correlation_id`.
The worker commits the request offset only after the response is delivered.

**[SCREENSHOT 1]** `make hw08-ps` - `docker ps` with `s1346-kafka`, `s1346-incident-worker`, `s1346-incident-api`, plus
the worker line *"Consumer is ready and listening..."* and the API line *"FastAPI server started at http://127.0.0.1:8446"*.

**[SCREENSHOT 2]** `make hw08-demo` - steps 1-8: CREATE request (operation, data), response with `incident_id`,
`success: true`, `correlation_id`.

**[SCREENSHOT 3]** Kafka message-flow logs - `docker logs s1346-incident-worker` showing `RECEIVED <- s1346_incident_requests`,
`PROCESSED`, `REPLY -> s1346_incident_responses`, next to the client's `SEND ->` / `RESPONSE <-` lines.

**[SCREENSHOT 4]** step 9 of the demo - the full CREATE -> GET sequence (SEND, RECEIVE, PROCESS, REPLY, CLIENT RESPONSE for
both correlation ids, in time order) and step 10 (retrieved incident, correlation preserved = True), plus the 3 error cases.

(Optional) **[SCREENSHOT]** `make hw08-demo-api` or `curl -X POST http://127.0.0.1:8446/incidents ...` - same flow via FastAPI.

Code snippets to include (short): `IncidentService.handle/create/get` (incident_service.py), the worker loop
(`RECEIVED -> handle -> produce to reply_to -> flush -> commit`), `IncidentKafkaClient.request`, the two FastAPI routes.

---

## Part 2 - Three-agent pipeline

| Agent (own process) | Reads | Writes | Group |
|---|---|---|---|
| You (`send_question.py`) | - | `s1346_inbox` (question) | - |
| Planner (`planner.py`) | `s1346_inbox` | `s1346_tasks` (plan, 2-4 steps) | `s1346_planners` |
| Writer (`writer.py`) | `s1346_tasks` (2 partitions) | `s1346_drafts` (draft answer) | `s1346_writers` |
| Reviewer (`reviewer.py`) | `s1346_drafts` | `s1346_final` (`status` + `answer`) | `s1346_reviewers` |

Every message is keyed by `correlation_id` and carries it unchanged, plus a `trace` list that each agent appends
`{stage, instance, at}` to. No agent imports or calls another; they only share topic names from `hw08_config.py`.

**[SCREENSHOT 5]** topic creation with the Kafka CLI (`make hw08-topics` output: `--list` + `--describe s1346_tasks` showing 2 partitions).

**[SCREENSHOT 6]** four terminals: planner / writer / reviewer logs (`RECEIVED <-`, `SENT ->`, `COMMITTED`) and
`send_question.py` printing the journey `s1346_inbox -> s1346_tasks -> s1346_drafts -> s1346_final`.

**[SCREENSHOT 7]** the final JSON (status, answer, correlation_id, trace).

### How Kafka helped the agents coordinate
- **No direct calls:** each agent only knows its input and output topic. The Planner finishes and moves on; it does
  not wait for the Writer, and the Reviewer does not need to know the Writer exists.
- **Buffering:** a question sent while the Writer is down simply waits in `s1346_tasks` and is processed when the Writer
  starts. Each agent's committed offset is its bookmark.
- **Correlation:** the `correlation_id` key and the `trace` list let `send_question.py` pick its own answer out of
  `s1346_final` and reconstruct the whole journey across three independent processes.
- **Scaling one stage:** the slow, LLM-heavy Writer can run as two instances in one group (two partitions)
  without changing the other agents.

---

## Part 3 - Failure behaviour

`python code/run_hw08_part3.py --scenario all` runs every scenario twice with the same code: once with the fix
switched off (writer flags `--no-idempotency`, `--auto-commit`, `--no-dlq`, no key) and once with it on.
Raw evidence: `reports/hw08/raw/part3_*.json`, `part3_ordering_{unkeyed,keyed}.csv`, `part3_events_*.jsonl`.

### Failure table  (copy the filled table from METRICS.md after `make hw08-metrics`)
| Failure scenario | Before fix | After fix |
|---|---|---|
| Duplicate delivery | **[YOU]** | **[YOU]** |
| Consumer killed mid-work | **[YOU]** | **[YOU]** |
| Poison message | **[YOU]** | **[YOU]** |
| Two partitions / two consumers | **[YOU]** | **[YOU]** |

**[SCREENSHOT 8]** duplicate replay: before = processed twice, 2 drafts; after = `DUPLICATE corr=... skipped`, 1 draft.

**[SCREENSHOT 9]** consumer death: `SIGKILL`, the committed offset printed at the kill (past the message with
auto-commit, equal to it with commit-after-success), the restarted writer's `RECEIVED` / `COMMITTED` of the same offset.

**[SCREENSHOT 10]** poison: `RETRY attempt 1/3, 2/3, 3/3` -> `DEAD-LETTER ... -> s1346_dead_letter`, then the good message
processed; before = `CRASH ... offset NOT committed` twice.

**[SCREENSHOT 11]** ordering: both runs' processing order and the per-incident `IN ORDER / OUT OF ORDER` lines.

### Fixes (short code snippets to include, from `code/kafka_agents/agent_base.py`)
- **Idempotency:** `if corr in self.store: ... skip, commit` and `self.store.add(corr)` after a successful output.
  The store is a JSON file, so it also survives a restart (a writer killed after producing but before committing
  does not produce the draft twice on redelivery). The Part 1 worker does the same in memory and re-sends the cached
  response.
- **Offset commit:** `enable.auto.commit=False`; `producer.flush()` -> `store.add()` -> `consumer.commit(message=msg)`.
- **Retry / dead letter:** `process_with_retries(...)` - 3 attempts, backoff 0.5 s / 1 s, then a record
  `{source_agent, topic, partition, offset, correlation_id, error, attempts, raw_value}` is sent to
  `s1346_dead_letter`, and the offset is committed so the partition moves on.
- **Partition key:** ordering run 2 sends with `key=entity_id` (murmur2 partitioner, as in the Java client), so every
  update of one incident lands in one partition and is consumed by one writer, in order.

### Comparison with the HW2 in-process graph
In HW2 (`code/agents_graph.py`) Planner -> Reviewer ran as LangGraph nodes in one Python process: each node was a
function call, and the next step simply waited for the return value.

**Two benefits gained with Kafka**
1. **Decoupled failure:** if the Writer crashes, the Planner keeps accepting questions and their tasks wait in
   `s1346_tasks`; after a restart nothing is lost (Part 3 II). In HW2 one exception ended the whole run.
2. **Independent scaling:** two Writer processes in one consumer group shared the two partitions of `s1346_tasks`
   (Part 3 IV) without changing the Planner or Reviewer. In HW2 the only way to go faster was a faster model.

**Two new responsibilities**
1. **Delivery semantics:** Kafka is at-least-once, so the same message can arrive twice (replay, or a redelivery
   after a crash). I had to add idempotency keyed by `correlation_id` and decide when to commit offsets.
   A function call in HW2 runs exactly once.
2. **Ordering and bad input:** order is guaranteed only within a partition, so related messages need a key (an
   unkeyed run had incidents processed out of order). A malformed message can block a partition forever unless I
   add bounded retries and a dead-letter topic. HW2 had neither problem because the call stack is ordered and an
   exception was immediately visible.

---

## Verification
`make verify-hw08` -> `reports/hw08/verification.json`: **[YOU] n/n checks passed** (homework 8, SID4 1346, commit,
model, SEED 1346, VERIFY_SEED 261346, each check with pass/fail). **[SCREENSHOT 12]**

## AI use
(Paste the final `reports/hw08/AI_USE.md` here.)
