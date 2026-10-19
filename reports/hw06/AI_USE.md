# HW6 AI_USE - s1346

> DRAFT written with the assistant. Edit every part marked **[YOU]** so it describes what you
> actually did and saw on your machine before you submit.

## 1. What I used an AI assistant for, and what I did myself

**AI assistant (Claude):** I used it as a pair programmer. It read the HW6 brief and my HW1-HW5
repository and drafted most of the new code: the PyMongo connection with `$jsonSchema` validators, the
Pydantic schemas and CRUD routes for `incident_reports`, the validation/error handlers and JSON middleware,
the memory system (`memory_store.py`, `memory_logic.py`, `chat.py`, embeddings, token counting), the chat
page, `memory_probes.yaml` and the 30-message conversation, the experiment runner and cost/METRICS
generator, the file-based memory module and CLI (`/memory`, `/compact`, `/dream`, `/help`), the 55-line
test MEMORY.md with its answer key, the AGENT.md checker, the offline test suite and `verify_hw06.py`.

**Myself [YOU]:** installed and ran MongoDB + Compass; ran every endpoint and error case with cURL;
held the 10+ message chat and checked summaries and episodes in Compass; ran the four experiment
settings and the probes on my own machine and model; reviewed the probe scores against the answers;
ran the consolidation test, `/compact`, `/dream` and the AGENT.md check; took all screenshots; chose
which settings are best/worst and wrote the analysis. *(adjust to what you really did)*

## 2. One AI output that was wrong/unsuitable

The fact-extraction prompt the assistant wrote for episodic memory (`EXTRACT_PROMPT` in
`code/backend/memory_logic.py`) contained an example sentence, *"The user's name is Dana."*.
qwen2.5:3b copied that example as if it were a fact: while I was only asking *"What should I tell riders
waiting at the stop?"*, it stored the episode **"The user's name is Dana."** (importance 0.8) next to the
correct "The user's name is Himja.". From then on the fact was retrieved by cosine similarity and the
assistant started addressing me as "Dana" in its replies (Fig 11). Because chat runs at temperature 0 with
seed 1346, the same wrong fact appeared again when I repeated the session.

## 3. How I detected the problem

I never typed "Dana" in the chat, but the replies used it. `GET /api/memory/himja` (Fig 12) showed where it came
from: the `recent_episodes` list contained "The user's name is Dana." created right after my message about
riders at the stop - a message with no name in it. The word "Dana" appeared nowhere in my messages, only in the
extraction prompt's example, so the extractor had hallucinated it from the prompt.

## 4. What I changed and why it works now

- Removed the concrete example name from the extraction prompt and added two rules: use only information
  written in the message itself and never invent names; questions/greetings contain no facts.
- Cleared the test user (`DELETE /api/memory/himja`) before the Part 3 runs, so no wrong episode leaks into them.
  This mattered for Part 3: the experiment conversation's persona is actually named Dana, so the leaked example
  would have made probe P5 look correct for the wrong reason.
- **[YOU]** after the fix, re-ran the chat / experiment and checked in `raw/probes_*.json` and Compass
  (`episodes`) that every stored name comes from a message that contains it.

**Verified independently - consolidation:** before running consolidation I wrote the correct current value of
every contradicted topic in `reports/hw06/memory_test/expected_resolutions.json`. `code/run_consolidation_test.py`
compares the result with that answer key and reported two wrong resolutions by the "newest statement wins" rule:
`project.port` (a later wrong "port 8000") and `db.relational` (a later tentative "thinking about PostgreSQL",
which the tool did flag `REVIEW`). Neither value was lost - both correct values stay in `## Superseded` - and
re-asserting the correct port with `/dream` fixes it at the next `/compact`.

**Also verified independently [YOU - optional]:** Ollama's `prompt_eval_count` vs. the Qwen2.5 tokenizer
count of the full prompt (columns `prompt_tokens` vs `prompt_tokens_full` in `raw/memory_turns.csv`).
If Ollama reports fewer tokens on later turns, that is the KV-cache reusing the unchanged prompt prefix.
That is why the cost estimate uses the tokenizer count: a hosted API bills the whole prompt.
