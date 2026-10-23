# HW7 - AI use (Himja Patel, s1346)

## 1. What I used an AI assistant for, and what I did myself
- **AI assistant (Claude):** drafted the HW7 code on top of my HW1-HW6 repository: JWT auth + role guards and the
  MySQL migration, the hand-written agent loop with its repair path, the fixed tasks and deterministic verifiers,
  the Reflexion wrapper, the three MRKL tools + LangGraph agent + React page, the hostile fixtures and attack
  runner, the file tools and safety gate, the offline test suite, `verify_hw07.py` and `make_metrics_hw07.py`.
  It also drafted the report text and this file.
- **Myself:** set up and ran everything on my MacBook (MySQL `s1346_rel`, MongoDB, FastAPI on port 8446, the React
  UI, Ollama with qwen2.5:3b); ran the migration and created the reader/writer/moderator users; did the Ruff /
  pre-commit demo and fixed the two B904 errors myself (`raise ... from None`); ran every experiment
  (Part 2 demo, recovery and 20-attempt reliability, Part 3 comparison and fault demo, both Part 4 scenarios in the
  UI, the 9 Part 5 attack runs plus the replay, Part 6); read every output, reported each problem back, re-ran after
  each fix, took all screenshots, reviewed the Part 3 verifier rejections by hand, edited the analysis and tagged `hw7`.

## 2. AI-produced outputs that were wrong or unsuitable
1. **Safety gate v1 (Part 6):** the first gate was an allow-list only (`SAFE_PREFIXES`). It allowed
   `echo pwned > /etc/hosts` because the command starts with the safe prefix `echo`.
2. **Ruff config:** imports were sorted differently depending on the directory Ruff ran from
   (`from auth import ...` counted as third-party inside `code/backend`), so `pre-commit` and `make lint` disagreed.
3. **Part 2 repair rule was too strict:** in my first real runs qwen2.5:3b sent `null` for optional arguments,
   used the line code `L-0033` and passed `category` to `incident_stats`. Each was treated as a fatal failure, and a
   failed call blocked the rest of the chain. The first Task B wording also let the model stop after a 50-row
   result. Several fixes were needed (see 4).
4. **Part 4 prompt/tool issues:** the model invented a `WHERE source='uploaded'` filter (no such column), answered
   without querying the data, and once called a tool with an unexpected argument, which crashed the graph with a
   `TypeError`. The UI also first saved evidence under the wrong scenario label.
5. **Part 6 integration test:** the model invented file paths (`file_with_DEBUG.py`, `/path/to/file.py`) instead of
   using the path returned by `search_in_files`, and the first pass check only looked at the first three calls.

## 3. How the problems were detected and the results verified
- The 10-command gate test prints v1 next to the final gate: `echo ... > /etc/hosts` was "allow" although
  "block" was expected.
- Running `ruff check .` from the repo root and from `code/backend` gave different I001 results.
- Parts 2, 4 and 6 problems were found by reading my own terminal output and UI timeline (RUN_LOG.txt), not by the
  assistant. Every fix was re-run on my machine before I accepted it.
- Part 4 numbers: the agent's in-answer arithmetic was wrong in several runs, so I only report the tool-computed
  totals (`cost_breakdown` over the same tool results), and I checked the extracted prices against the pricing
  snapshot (SHA-256 recorded in the evidence files).
- Part 3: the verifier flagged one rejection as possibly false; I checked it by hand. The answer gave a Breakdown
  example although Delay is the top category on L-033, so the rejection was correct (0 false rejections after review).
- Part 5: the agent runs never issued DELETE/UPDATE, so I added a no-model replay that sends the injected SQL
  straight to `csv_sql` to check what the tool boundary actually enforces.

## 4. What changed and why it works now
- **Gate:** an independent `is_destructive()` deny-list (recursive deletion, privilege escalation,
  permission/ownership changes, raw-device writes, filesystem creation, redirection to root paths) is checked
  BEFORE the allow-list; re-run shows 10/10 with 0 false allows.
- **Ruff:** `src = [...]` module roots in `ruff.toml`, so first-party imports are classified the same everywhere.
- **Part 2:** null/empty optional arguments are dropped before validation (still counted as a malformed first try),
  schema errors name the valid arguments and which tool owns a wrong one, one reprompt per distinct problem with
  `MAX_REPAIRS = 3`, results shown to the model are cut to 10 rows, and Task B was redesigned around line L-033.
- **Part 4:** the prompt lists the real columns, `csv_sql` errors list the available columns, an evidence-correction
  turn and a verifier turn were added, unexpected tool arguments return an error instead of crashing, and the UI
  sets the scenario label from the file name.
- **Part 6:** `read_file` errors list the existing files, a failed required call triggers one reprompt, and the pass
  check uses the successful calls (glob -> search -> read) and the file actually read.

## 5. What still does not work (reported, not hidden)
- qwen2.5:3b still recommends membership in the `payg_wins` scenario after the verifier turn; the tool-computed
  decision and the mismatch banner catch it.
- The prompt-only defense did not stop the recommendation-override injection in any configuration.
- Task B answers often leave out the count; Part 6 hit the 8-iteration ceiling after reading the right file.
