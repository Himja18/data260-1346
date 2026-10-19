# AGENT.md - s1346 Municipal Transit Incidents (DATA-260)
<!-- Durable project and agent instructions. Loaded into the system prompt by code/file_memory.py.
     Learned facts belong in MEMORY.md, not here. Each instruction has an ID used by code/agent_md_check.py. -->

## Project description
- P1. This repository is the DATA-260 project of student s1346 (SID4 1346, DOMAIN_ID 2): a Municipal Transit Incidents system with a FastAPI backend on PORT_BASE 8446 and a React client.
- P2. Incident categories are exactly Delay, Breakdown, Accident and Service Change; never invent new categories.

## Technology stack
- T1. Python 3.11, FastAPI, Pydantic v2, SQLAlchemy 2 with MySQL (database s1346_rel), PyMongo with MongoDB (database s1346_doc); the local model is qwen2.5:3b served by Ollama.
- T2. Every LLM call goes through src/model_client.py (ModelClient.complete / ModelClient.embed); no other module calls the Ollama HTTP API directly.

## Coding conventions
- C1. Function and variable names use snake_case; module-level constants use UPPER_SNAKE_CASE.
- C2. Every function has type hints on all parameters and on its return value.
- C3. Every public function starts with a one-line docstring that says what it does.
- C4. Library code reports problems with the logging module or by raising exceptions, never with print(); only command-line scripts may print.
- C5. Catch specific exceptions; never write a bare `except:`.

## Testing approach
- X1. Every new function gets an offline test that needs no network, database or LLM (fakes or dependency injection, e.g. mongomock or a fake ModelClient).
- X2. `make verify-hw06` must pass on the tagged commit; checks test behaviour (status codes, fields, counts), never the exact wording of model output.

## Prohibited actions
- N1. Never hard-code passwords, API keys, tokens or connection secrets; read them from environment variables.
- N2. Never modify or delete documents in the Part 1 incident_reports collection from memory code.
- N3. Never silently delete a fact from MEMORY.md; a superseded fact moves to the "Superseded" section with what replaced it.
- N4. Never rewrite published git history: no force-push to main, and no moving a homework tag after that homework is submitted.

## Code review (reused from HW1)
- R1. When reviewing code, respond ONLY with a bulleted list: one specific issue per bullet, naming the exact line, function or file, at most one sentence each, with no introduction or summary.
- R2. If the reviewed code has no issues, respond with the single bullet "No issues found."

## Assistant behaviour
- B1. Answer in at most 120 words; when an incident report is ambiguous, ask which category applies instead of guessing.
