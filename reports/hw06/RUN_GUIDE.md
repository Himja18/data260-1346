# HW6 run guide - s1346 (what to run on the MacBook, in order)

All commands from the repo root `~/Documents/data260-1346` with the venv active
(`source venv/bin/activate`). Append real console output to the run log with
`2>&1 | tee -a reports/hw06/RUN_LOG.txt` (the experiment script appends on its own).

## 0. One-time setup (~10 min)
```bash
brew tap mongodb/brew
brew install mongodb-community@7.0 && brew services start mongodb-community@7.0
brew install --cask mongodb-compass            # for the Compass screenshots
pip install -r code/backend/requirements.txt   # adds pymongo, pyyaml, transformers, mongomock, httpx
ollama list                                    # qwen2.5:3b must be listed; keep `ollama serve` running
make hw06-test                                 # offline suite, expect 13/13 passed
```

## 1. Start the backend (terminal 1, leave it running)
```bash
cd code/backend && export MYSQL_PASSWORD='...' && python main.py
```
Startup log should say `MongoDB s1346_doc ready: [...]`. Check: `curl -s localhost:8446/health` -> `"mongo":"ok"`.
The first `/api/chat` call loads bge-small (cached from HW4) and downloads the Qwen2.5 tokenizer (~7 MB) once.

## 2. Part 1 - MongoDB document API (terminal 2)
```bash
B=localhost:8446/api/doc/incidents; H='Content-Type: application/json'
curl -s -X POST $B -H "$H" -d '{"title":"Line 22 - bus stalled on Main St","description":"Engine overheating, riders transferred","location":"Main St & 5th Ave","category":"Breakdown","occurred_at":"2026-10-16T08:15:00Z"}' | python -m json.tool
curl -s -X POST $B -H "$H" -d '{"title":"Light rail 10 min late downtown","category":"Delay","status":"Investigating","occurred_at":"2026-10-16T17:40:00Z"}' | python -m json.tool
curl -s -X POST $B -H "$H" -d '{"title":"Line 68 detour - water main break","location":"Monterey Rd","category":"Service Change","occurred_at":"2026-10-16T21:05:00Z"}' | python -m json.tool
curl -s $B | python -m json.tool                                  # GET all
ID=<paste an id>
curl -s $B/$ID | python -m json.tool                              # GET one
curl -s -X PUT $B/$ID -H "$H" -d '{"status":"Resolved"}' | python -m json.tool
curl -s -X DELETE $B/$ID ; curl -s -w ' %{http_code}\n' $B/$ID    # delete, then 404
# validation errors (one screenshot):
curl -s -w ' %{http_code}\n' -X POST $B -H "$H" -d '{"description":"no title"}'
curl -s -w ' %{http_code}\n' -X POST $B -H "$H" -d '{"title":"x","category":"Flood","status":"Done","occurred_at":"2026-10-16T08:00:00Z"}'
curl -s -w ' %{http_code}\n' -X POST $B -H "$H" -d '{"title":123,"category":"Delay","occurred_at":"yesterday"}'
curl -s -w ' %{http_code}\n' $B/not-an-id
```
Compass: connect `mongodb://127.0.0.1:27017` -> `s1346_doc` -> `incident_reports` (Documents tab, and the
Validation tab showing the `$jsonSchema`).

## 3. Part 2 - memory chat
Open http://localhost:8446/chat (user_id `himja`), send at least 10 messages in one session, e.g.:
1. Hi, I'm Himja and I'm on the incident desk tonight. 2. Bus 4471 broke down at Santa Clara & 5th.
3. Which category is that? 4. My supervisor tonight is Lena Park. 5. What should I tell riders at the stop?
6. Light rail is running 10 minutes late downtown. 7. How long should a detour stay open?
8. I prefer reports as three bullet points. 9. Give me a report on tonight so far. 10. Who is my supervisor?
11. Which bus broke down earlier?

Messages 4 and 8 trigger session summaries, and message 8 also makes the first lifetime summary.
Messages 10-11 show episodic retrieval. Then:
```bash
curl -s localhost:8446/api/memory/himja | python -m json.tool
curl -s localhost:8446/api/aggregate/himja | python -m json.tool
```
Compass: `messages`, `summaries`, `episodes` collections with documents.

## 4. Part 3 - experiments (~30-60 min, laptop plugged in)
```bash
python code/run_memory_experiment.py          # n4, n12, n30, policy; resumable with --only n30
make hw06-metrics                             # writes reports/hw06/METRICS.md + raw/memory_cost.json
```

## 5. Part 4 - file-based memory
```bash
python code/run_consolidation_test.py 2>&1 | tee -a reports/hw06/RUN_LOG.txt
python code/agent_md_check.py --generate 2>&1 | tee -a reports/hw06/RUN_LOG.txt
cp reports/hw06/memory_test/MEMORY_original.md /tmp/MEMORY_demo.md
python code/file_memory_chat.py --memory-file /tmp/MEMORY_demo.md
#   /help   /memory   (2-3 normal messages, e.g. "I'm Himja, the backend still runs on port 8446")
#   /dream  /compact  /exit      <- screenshot the /compact before -> after counts
make hw06-metrics
```

## 6. Commit, verify, tag
```bash
git add -A && git commit -m "HW6: MongoDB document API, memory chat, memory cost experiments, file-based memory"
make verify-hw06 2>&1 | tee -a reports/hw06/RUN_LOG.txt
make hw06-metrics
git add -A && git commit -m "HW6: verification.json, METRICS, RUN_LOG"
git tag hw6 && git push && git push origin hw6
git rev-parse hw6                               # tagged commit hash for the report header
```

## Screenshot checklist (make sure `himja@Himjas-MacBook-Pro` is visible in every terminal screenshot)
- P1: create, get all, get one, update, delete+404, validation errors; Compass `incident_reports` + Validation tab
- P2: chat page conversation; `/api/memory/himja` JSON; `/api/aggregate/himja` JSON; Compass messages/summaries/episodes
- P3: end of `run_memory_experiment.py` output (SUMMARY lines)
- P4: `/compact` report; `run_consolidation_test.py` output; `agent_md_check.py` output
- `make verify-hw06` result
