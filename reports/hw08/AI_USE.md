# HW8 - AI use (Himja Patel, s1346)

> DRAFT written with the AI assistant. Before submitting, edit every line marked **[YOU]** so it describes
> what you actually did and saw on your Mac. Delete this note.

## 1. What I used an AI assistant for, and what I did myself
- **AI assistant (Claude):** read the HW8 handout and my HW1-HW7 repository and drafted the HW8 code on top of it:
  `hw08_config.py`, `kafka_common.py`, the Incident worker / Kafka client / FastAPI wrapper / `homework_demo.py`
  (Part 1), the Planner, Writer and Reviewer agents and `send_question.py` (Part 2), the shared agent loop with
  idempotency, commit-after-success and retries + dead-letter topic, the Part 3 runner (`run_hw08_part3.py`),
  `docker-compose.yml`, the Makefile targets, the offline tests, `verify_hw08.py` and `make_metrics_hw08.py`.
  It also drafted the report text and this file.
- **Myself [YOU]:** started Docker Desktop, Kafka, the worker and the API on my MacBook; created the seven topics
  with the Kafka CLI (`make hw08-topics`); ran `homework_demo.py`; ran the three agents in three terminals and
  sent questions; ran the Part 3 runner and read every before/after result; killed the Writer myself with Ctrl-C /
  `kill -9` to see the redelivery; checked the dead-letter topic; took all screenshots; ran `make verify-hw08`;
  edited the analysis; committed, tagged `hw8` and pushed.

## 2. AI-produced output that was wrong or unsuitable / things I verified
1. **Topic-creation script crashed:** the first `create_topics_hw08.py` called `admin().create_topics(...)` on a
   temporary AdminClient. The client was garbage-collected before the futures finished, so every topic failed
   with `KafkaError _DESTROY "Handle is terminating"`.
2. **Agent imports would have broken after linting:** the first Planner/Writer/Reviewer files imported
   `hw08_config` *after* `agent_base`, relying on `agent_base` to put `code/` on `sys.path`. Ruff's import sorting
   (run by my pre-commit hook) moves `import hw08_config` above `from agent_base import ...`, which would make
   `python planner.py` fail with `ModuleNotFoundError: hw08_config`.
3. **Loop-variable lambdas:** the first Part 3 runner used `lambda: has_event(ev, corr)` inside `for` loops; Ruff's
   bugbear rule B023 flags this (the lambda captures the variable, not its value at that iteration).
4. **[YOU]** add anything that did not work on the first real run (for example a timeout, a container that
   restarted, a wrong count in the runner output) and what was changed.

## 3. How I detected the problem or verified the result
1. Ran the topic script against a broker and read the traceback (`_DESTROY`), then checked with
   `kafka-topics.sh --describe` that all seven topics exist and `s1346_tasks` has 2 partitions.
2. Read the import order against Ruff's isort rules (`import x` sorts before `from y import`) and the lint hook in
   `.pre-commit-config.yaml`; `make lint` must be clean before the commit.
3. B023 is part of the `B` rules selected in `ruff.toml`.
4. **[YOU]** I verified the behaviour itself, not only the code: the duplicate replay produced 2 drafts before
   and 1 after; the committed offset printed by the runner was past the message before the fix and equal to
   it after; the poison message appeared in `s1346_dead_letter` with `attempts = 3`; the keyed ordering run had
   every incident in one partition with seq 1..5 in order. `make verify-hw08` -> all checks PASS.

## 4. What I changed and why it works now
1. Keep a reference to the AdminClient until every future resolves (`client = admin()`), so the handle lives
   long enough for the CreateTopics responses.
2. Every agent file now adds `code/` to `sys.path` itself before importing (`# noqa: E402`), so it works in any
   import order and from any directory; `ruff.toml` lists `code/kafka_service` and `code/kafka_agents` as source
   roots so Ruff classifies these modules as first-party consistently.
3. The lambdas bind the loop values as default arguments (`lambda ev=ev, corr=corr: ...`).
4. **[YOU]**
