# HW6 AI_USE - s1346 (Himja Patel)

## 1. What I used an AI assistant for, and what I did myself

**AI assistant (Claude):** pair programmer. It read the HW6 brief and my HW1-HW5 repository and drafted most of
the new code: the MongoDB connection with `$jsonSchema` validators, the Pydantic schemas and CRUD routes for
`incident_reports`, the error handlers and JSON middleware, the memory system (`memory_store.py`,
`memory_logic.py`, `chat.py`, embeddings, token counting), the chat page, `memory_probes.yaml` and the 30-message
conversation, the experiment runner and METRICS generator, the file-based memory module and CLI
(`/memory`, `/compact`, `/dream`, `/help`), the 55-line test MEMORY.md with its answer key, the AGENT.md checker,
the offline test suite, `verify_hw06.py`, and first drafts of METRICS.md and the report.

**Myself:** I installed and debugged MongoDB 7.0 and Compass on my Mac (Homebrew tap trust, a failing launchd
service, starting `mongod` with its own data path), ran every endpoint and error case with cURL, held the chat
session and inspected the collections in Compass, ran all four experiment settings and the probes on my own
machine (and re-ran them with `caffeinate` after the Mac slept during the first run), ran the consolidation test,
`/dream`, `/compact` and the AGENT.md check, fixed the generated function by hand, reviewed every result and
took all screenshots.

## 2. One AI output that was wrong

The fact-extraction prompt the assistant wrote for episodic memory (`EXTRACT_PROMPT` in
`code/backend/memory_logic.py`) contained the example sentence "The user's name is Dana.". qwen2.5:3b copied it
as a fact: after my message "What should I tell riders waiting at the stop?" it stored the episode
"The user's name is Dana." (importance 0.8) next to the correct "The user's name is Himja.", and the replies
began addressing me as Dana. Because chat runs at temperature 0 with seed 1346, the same wrong fact came back
when I repeated the session.

## 3. How I detected it

I never typed "Dana", yet replies used it. `GET /api/memory/himja` (Fig 12) and the `episodes` collection
(Fig 16) showed the stored fact and its timestamp, right after a message with no name in it. The only place
"Dana" appeared was the example in the extraction prompt. A later turn confirmed the harm: for the message
"hellp" the wrong fact was retrieved with a higher score (0.555) than the correct one (0.516) (Fig 16b).

## 4. What I changed and why it works now

I removed the example name from the extraction prompt and added two rules: use only information written in the
message itself and never invent names; questions and greetings contain no facts. I cleared the test users before
the Part 3 runs. This mattered: the experiment persona really is named Dana, so the old prompt would have made
probe P5 look correct for the wrong reason. After the fix, the only name used in the Part 3 runs was the
persona's own name from message 2 ("Dana Okafor"), and the verify run stored only facts that were in its messages
("The user owns a vehicle registered as Bus 9901.", "The user works as a bus dispatcher for Route 99 night buses.").

**Also verified independently:**
- The token counter first reported "prompt 2 tok" because a newer `transformers` returns a dict from
  `apply_chat_template`; after the fix the tokenizer count matched Ollama's `prompt_eval_count` exactly
  (119 = 119, 385 = 385 in RUN_LOG.txt), and two separate N=4 runs gave the same 669.1 tokens per turn.
- The consolidation answer key (`expected_resolutions.json`, written before running) exposed two wrong
  "newest wins" resolutions (`project.port`, `db.relational`); re-stating the port through `/dream` fixed it.
- The model-generated `incident_age_hours` failed the AGENT.md check (no docstring; naive vs aware datetime
  crash). Feedback fixed the docstring; I fixed the datetime bug by hand and re-verified (7/7 rules, 4/4 tests).
