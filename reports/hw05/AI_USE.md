# HW5 AI_USE - s1346

## 1. What I used an AI assistant for, and what I did myself

**AI assistant (Claude):** I used it as a pair programmer. It read the HW5 brief and my HW4 repository,
proposed the design, and drafted most of the new code: the HW5 migration and transit-line CRUD routes, the
Redux Toolkit slice and axios thunks, both MCP servers (`meals_server.py`, `domain_server.py`), the shared
`{ok, data, error}` envelope, the retry/backoff layer, the fault-injection and demo scripts, the offline test
runner, the agent loop, and first drafts of METRICS.md, RUN_LOG.txt and this file.

**Myself:** I ran and checked everything on my machine. I backed up and migrated my real MySQL database,
tested every endpoint and error case in Postman, verified the Redux screens in the browser, set up and
debugged the tooling (Node upgrade with nvm, MCP Inspector, MySQL credentials), ran every MCP tool in the
Inspector, ran all experiments and scenarios against my own data and model, reported each failure back with the
exact error output, reviewed the results, and took all screenshots. The reflection describes my own agent run
(`bb352ae8`), and I chose the domain safety rule (no unscoped bulk export of the incident log).

## 2. One AI output that was wrong / unsuitable

The assistant's MCP setup instructions did not work as given. It first told me to install with
`pip install "mcp[cli]"` and run `mcp dev meals_server.py`, as in the brief. That produced three failures in a row:
(a) the latest SDK is 2.x, where `FastMCP` no longer exists, so the server would not import; (b) `mcp dev` downloaded
MCP Inspector 2.9, which crashed on my Node 20.9 (`node:util does not provide an export named 'styleText'`);
(c) after upgrading Node, `mcp dev` tried to launch the server through `uv` (`spawn uv ENOENT`), and Inspector 2.9
then left `tools/list` pending and timed out a `tools/call` even though the server log showed the result was computed.

## 3. How I detected the problem

Each failure was visible in the terminal or Inspector, and I pasted the exact output back. For (c) the deciding
evidence was the Inspector's Server Console: it showed `meals_by_ingredient('chicken') -> 12` and a
`200 OK` from TheMealDB, while the UI reported "Request timed out after 1m00s". That proved the server was correct
and the client was the problem.

## 4. What I changed and why it works now

- Pinned the SDK to `mcp[cli]>=1.9,<2` in `code/mcp/requirements.txt`, so the FastMCP API from the brief exists.
- Installed Node 22 with `nvm install 22` and cleared the corrupted npx cache (`rm -rf ~/.npm/_npx`).
- Launched the Inspector directly with my project's Python instead of `uv`:
  `npx @modelcontextprotocol/inspector@0 "$PWD/venv/bin/python" code/mcp/domain_server.py`.
  Inspector 0.22 talks reliably to the 1.x server and runs over STDIO with the venv that has the pinned SDK.
- Verified independently: all 4 meals tools and all 3 domain tools returned the designed output in the Inspector,
  and `verify_hw05.py` now starts both servers over STDIO and checks a real tool call on each.

**Something I verified independently:** the fault-injection numbers. I ran the 150-call experiment twice; the
fault-sequence hashes (`dd89800342a2adde`, `63ffc9b4ddea006b`, `ca089130d46f7fcd`) were identical across runs and
matched the assistant's offline SQLite run, so the VERIFY_SEED reproducibility claim holds on my machine.
