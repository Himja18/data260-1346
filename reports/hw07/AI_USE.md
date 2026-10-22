# HW7 - AI use (s1346)

> DRAFT written with the assistant. Edit every section so it describes what *you* actually did -
> sections marked **[YOU]** can only be answered by you.

## 1. What I used an AI assistant for, and what I did myself
- **AI assistant (Claude):** drafted the HW7 code on top of my HW1-HW6 repository: JWT auth + role guards and the
  MySQL migration, the hand-written agent loop with its repair path, the fixed tasks and deterministic verifiers,
  the Reflexion wrapper, the three MRKL tools + LangGraph agent + React page, the hostile fixtures and attack
  runner, the file tools and safety gate, the offline test suite, `verify_hw07.py` and `make_metrics_hw07.py`;
  it also drafted this file and the report text.
- **Myself [YOU]:** ran every experiment on my MacBook (MySQL, Ollama qwen2.5:3b), checked the outputs, took the
  screenshots, did the Ruff/pre-commit demo and the fix, compared the pricing numbers with the live Bay Wheels
  page, reviewed the flagged verifier rejections by hand, wrote/edited the analysis, tagged `hw7`.

## 2. One AI-produced output that was wrong/unsuitable, or one thing I verified independently
- **Wrong output:** the first version of the bash safety gate was an allow-list only (`SAFE_PREFIXES`). It allowed
  `echo pwned > /etc/hosts` because the command starts with the safe prefix `echo`.
- **Also:** the first Ruff setup sorted imports differently depending on the directory it was run from
  (`from auth import ...` was "third-party" when run inside `code/backend`), so `pre-commit` and `make lint` disagreed.
- **[YOU] independently verified:** e.g. the monthly price, unlock fee and per-minute rates extracted from the
  pricing snapshot against the live https://www.lyft.com/bikes/bay-wheels/pricing page on <date>.

## 3. How the problem was detected / the result verified
- The 10-command gate test prints the first version (allow-list only) next to the final gate: the `echo ... > /etc/hosts`
  row was "allow" although it is expected "block" (a false allow).
- Running `ruff check .` from the repo root and from `code/backend` gave different I001 results.
- **[YOU]:** how you compared the prices / checked the flagged Part 3 rejections.

## 4. What changed and why it works now
- Added an independent `is_destructive()` deny-list (recursive deletion, privilege escalation, permission/ownership
  changes, raw-device writes, filesystem creation, redirection to root paths) that `confirm_bash` checks BEFORE the
  allow-list, so a safe prefix can no longer hide a destructive command; the re-run shows 10/10 with 0 false allows.
- Added `src = [...]` module roots to `ruff.toml`, so first-party imports are classified the same from any directory.
- **[YOU]:** anything you changed after your own runs.
