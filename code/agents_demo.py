"""
agents_demo.py — DATA-260 HW1 Part 2: Agentic AI

Two tiny "agents" (Planner, Reviewer) plus a Finalization step, talking to a
local LLM served through Ollama. Input: a title + content describing a
municipal transit incident. Output: exactly 3 topical tags and a summary of
at most 25 words, produced through a Planner -> Reviewer -> Finalizer flow,
printed as valid JSON.

Model substitution note (see report.pdf / AI_USE.md for details):
The assignment default is qwen3:8b. This machine (MacBook Pro M2, 8GB RAM)
cannot comfortably run an 8B model alongside Docker/VS Code/browser, so we
substitute the smaller tool-capable model qwen2.5:3b, pulled locally via
`ollama pull qwen2.5:3b`.

Usage:
    python agents_demo.py --title "..." --content "..."
    python agents_demo.py --input-file reports/hw01/cases/nondeterminism_input.json --temperature 0.7
"""

import argparse
import json
import re
import sys
import time

from langchain_ollama import ChatOllama

MODEL_NAME = "qwen2.5:3b"


def build_llm(temperature: float) -> ChatOllama:
    """Create a ChatOllama client at the given temperature."""
    return ChatOllama(model=MODEL_NAME, temperature=temperature)


def extract_json(text: str) -> dict:
    """
    Best-effort extraction of a JSON object from an LLM response.
    Local models sometimes wrap JSON in prose or code fences, so we
    look for the first {...} block and parse that.
    """
    text = text.strip()
    # Strip markdown code fences if present
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON object found in model output:\n{text}")
    return json.loads(match.group(0))


def run_planner(llm: ChatOllama, title: str, content: str) -> dict:
    """
    Planner agent: reads the raw title/content and proposes an initial
    set of 3 tags and a draft summary (<=25 words). Tags/summary must be
    derived from the actual text, not hardcoded domain keywords.
    """
    prompt = f"""You are the PLANNER agent in a content-tagging pipeline.

Given the TITLE and CONTENT below, produce:
1. Exactly 3 short topical tags (2-3 words each) that best describe the
   specific content — derive them from what is actually written, do not
   invent generic categories that aren't supported by the text.
2. A one-sentence summary of at most 25 words.

TITLE: {title}
CONTENT: {content}

Respond with ONLY a JSON object in this exact shape, no other text:
{{"tags": ["tag1", "tag2", "tag3"], "summary": "..."}}
"""
    response = llm.invoke(prompt)
    return extract_json(response.content)


def run_reviewer(llm: ChatOllama, title: str, content: str, planner_output: dict) -> dict:
    """
    Reviewer agent: critiques the Planner's draft against the source text
    and either approves it as-is or returns a corrected version. This is
    what lets us answer "did the Reviewer change anything?" honestly.
    """
    prompt = f"""You are the REVIEWER agent in a content-tagging pipeline.

Original TITLE: {title}
Original CONTENT: {content}

The PLANNER produced this draft:
{json.dumps(planner_output)}

Check the draft against the original text:
- Are all 3 tags actually supported by the content (not generic/invented)?
- Is the summary accurate and at most 25 words?
- Are there exactly 3 tags, no more, no fewer?

If the draft is good, return it unchanged. If not, return a corrected
version. Either way, respond with ONLY a JSON object in this exact shape,
no other text:
{{"tags": ["tag1", "tag2", "tag3"], "summary": "...", "changed": true/false, "review_notes": "one short sentence explaining what you checked or changed"}}
"""
    response = llm.invoke(prompt)
    return extract_json(response.content)


def finalize(reviewer_output: dict, planner_output: dict) -> dict:
    """
    Finalization step (deterministic, no LLM call): assembles the final
    Publish-ready JSON from the Reviewer's output, enforcing the 3-tag /
    25-word constraints as a hard safety net.

    If the Reviewer returned fewer than 3 tags (a real failure mode we
    observed in testing), backfill missing slots from the Planner's
    original tags rather than silently publishing an under-filled list.
    """
    tags = list(dict.fromkeys(reviewer_output.get("tags", [])))  # de-dupe, preserve order

    if len(tags) < 3:
        for t in planner_output.get("tags", []):
            if t not in tags:
                tags.append(t)
            if len(tags) == 3:
                break

    tags = tags[:3]

    summary = reviewer_output.get("summary", "")
    words = summary.split()
    if len(words) > 25:
        summary = " ".join(words[:25])

    return {
        "tags": tags,
        "summary": summary,
    }


def run_pipeline(title: str, content: str, temperature: float, verbose: bool = True) -> dict:
    """Runs the full Planner -> Reviewer -> Finalizer flow once and
    returns a dict with timing info and all intermediate outputs."""
    llm = build_llm(temperature)

    start = time.time()

    planner_output = run_planner(llm, title, content)
    if verbose:
        print("\n=== PLANNER OUTPUT ===")
        print(json.dumps(planner_output, indent=2))

    reviewer_output = run_reviewer(llm, title, content, planner_output)
    if verbose:
        print("\n=== REVIEWER OUTPUT ===")
        print(json.dumps(reviewer_output, indent=2))

    final_output = finalize(reviewer_output, planner_output)
    latency_ms = (time.time() - start) * 1000

    if verbose:
        print("\n=== FINALIZED / PUBLISH OUTPUT ===")
        print(json.dumps(final_output, indent=2))
        print(f"\n(latency: {latency_ms:.0f} ms, temperature: {temperature})")

    return {
        "planner": planner_output,
        "reviewer": reviewer_output,
        "final": final_output,
        "latency_ms": latency_ms,
        "temperature": temperature,
    }


def main():
    parser = argparse.ArgumentParser(description="Planner -> Reviewer -> Finalizer tagging pipeline")
    parser.add_argument("--title", type=str, help="Incident title")
    parser.add_argument("--content", type=str, help="Incident content/description")
    parser.add_argument("--input-file", type=str, help="Path to a JSON file with {\"title\":..., \"content\":...}")
    parser.add_argument("--temperature", type=float, default=0.7, help="Sampling temperature (default 0.7)")
    parser.add_argument("--quiet", action="store_true", help="Suppress intermediate step printing (used for batch runs)")
    args = parser.parse_args()

    if args.input_file:
        with open(args.input_file, "r") as f:
            data = json.load(f)
        title, content = data["title"], data["content"]
    elif args.title and args.content:
        title, content = args.title, args.content
    else:
        # Default demo input for a quick manual run
        title = "Line 22 - Bus stalled on Main St"
        content = (
            "The 8:15 AM bus on Route 22 broke down near the Main St and "
            "5th Ave intersection. Passengers were stranded for 20 minutes "
            "before a replacement vehicle arrived. Driver reported a "
            "mechanical issue with the engine."
        )

    result = run_pipeline(title, content, args.temperature, verbose=not args.quiet)

    if args.quiet:
        # For batch/non-determinism runs: print one JSON line per run
        print(json.dumps({
            "tags": result["final"]["tags"],
            "summary": result["final"]["summary"],
            "latency_ms": result["latency_ms"],
            "temperature": result["temperature"],
        }))


if __name__ == "__main__":
    main()