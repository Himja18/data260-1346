# AI_USE.md — DATA-260 HW1

## 1. What I used an AI assistant for, and what I did myself

I used Claude (Anthropic) as a starting-point generator and troubleshooting
aid for the initial drafts of: the HTML/CSS/JS form, the Dockerfile,
`agents_demo.py`, the non-determinism batch-runner script,
`src/model_client.py`, and `hw1_client.py`.

Everything else — which was the majority of the actual work — I did
myself:
- Set up the GitHub repository, folder structure, and collaborators
- Created my AWS account, generated and later rotated my own access
  keys, and made every configuration decision in the AWS Console myself
  (cluster settings, task definitions, security group rules, networking)
- Ran every single command in my own terminal, one at a time, and
  personally verified each step worked before moving to the next —
  nothing was assumed to work just because it was AI-generated
- Diagnosed and fixed the AWS ECS deployment failure myself by reading
  the actual CloudWatch logs and recognizing the `exec format error`
  as an architecture mismatch
- Personally caught the Finalizer's tag-count bug by manually inspecting
  the JSON output of a real run, not by any automated check
- Installed and configured Ollama, Python 3.11, and the virtual
  environment on my own machine, resolving errors as they came up
- Ran the full 40-run non-determinism experiment and the 5-turn
  conversation myself, typing every message and reading every result
- Decided on the model substitution (qwen2.5:3b instead of qwen3:8b)
  based on my own hardware constraints (8GB RAM MacBook Pro M2) and past
  experience with Ollama slowing down my laptop
- Reviewed, tested, and approved every file before committing it to the
  repository — I did not commit anything I hadn't personally run and
  checked first

## 2. One AI-produced output that was wrong / one thing I independently verified

Two clear examples came up during this assignment:

**Example A — Docker image architecture mismatch.** The AI-generated
Dockerfile built successfully and ran fine locally, but when deployed to
AWS ECS Fargate, the task immediately crashed with exit code 255. I
personally checked the CloudWatch logs (not the AI) and found the raw
error: `exec /docker-entrypoint.sh: exec format error`. This is a classic
ARM64-vs-x86_64 architecture mismatch: my MacBook's M2 chip builds ARM64
images by default, but Fargate expects x86_64/amd64.

**Example B — the Finalizer's tag-count bug.** The first version of
`agents_demo.py`'s `finalize()` function simply truncated the Reviewer's
tags to 3 with `[:3]`, silently assuming the Reviewer would always return
at least 3. In my first real run, the Reviewer returned only 2 tags
(after removing "Bus Delays" as unsupported), and the Finalizer published
only 2 tags instead of the required 3 — a real, observable bug, not a
hypothetical one.

## 3. How I detected the problem or verified the result

**Example A:** I ran `curl -v http://<public-ip>:8446` directly against
the deployed service to see the raw HTTP response, then checked the ECS
task's CloudWatch logs when the task showed status "Stopped" with exit
code 255. The log line `exec format error` is a well-known signature of
an architecture mismatch, which I recognized from the error text itself.

**Example B:** I actually read the printed JSON output of every stage
(Planner, Reviewer, Finalized) rather than just checking that the script
ran without crashing. Counting the tags in the "FINALIZED / PUBLISH
OUTPUT" section by eye, I noticed only 2 items in the `tags` array when
exactly 3 were required.

## 4. What I changed and why it works now

**Example A:** I rebuilt the Docker image explicitly for the target
architecture using `docker buildx build --platform linux/amd64 -t
transit-incident-app:latest .`, re-tagged it, and re-pushed it to ECR.
After forcing a new ECS deployment with the corrected image, the task
started successfully and stayed in a "Running" steady state — confirmed
by loading the app at its public IP in a browser.

**Example B:** I rewrote `finalize()` to de-duplicate the Reviewer's tags
and, if fewer than 3 remain, backfill missing slots from the Planner's
original tag list before truncating to exactly 3. This guarantees the
published output always has exactly 3 tags regardless of what the
Reviewer returns, without silently hiding the under-fill the way the
original `[:3]` slice did. I verified the fix by re-running the pipeline
and confirming the FINALIZED output consistently contained 3 tags across
subsequent runs, including the full 40-run non-determinism batch in
Part 3.