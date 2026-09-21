"""
code/agents_graph.py — DATA-260 HW2 Part 3: Stateful Agent Graph

Refactors HW1's sequential Planner -> Reviewer -> Finalizer script into a
stateful, supervised graph using langgraph, implementing the supervisor
pattern from lecture:

    entry -> supervisor -(no proposal)-> planner -> supervisor
                          -(has proposal, unreviewed)-> reviewer -> supervisor
                          -(reviewer flagged issues, under ceiling)-> planner
                          -(clean or ceiling reached)-> END

All LLM calls happen inside planner_node/reviewer_node, but are routed
through the src/model_client.py ModelClient.complete(messages) adapter from
HW1 rather than calling Ollama or LangChain directly — per HW2 Part 3
requirements.

Usage:
    python code/agents_graph.py --title "..." --content "..."
    python code/agents_graph.py --input-file reports/hw02/cases/schema_input.json
    python code/agents_graph.py --force-issues   # test the self-correction loop
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, TypedDict

from langgraph.graph import StateGraph, END
from pydantic import BaseModel, field_validator, ValidationError

# Make src/ importable regardless of cwd.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from model_client import ModelClient  # noqa: E402

TURN_CEILING_DEFAULT = 6



class PlannerOutputSchema(BaseModel):
    tags: List[str]
    summary: str

    @field_validator("tags")
    @classmethod
    def exactly_three_tags_in_range(cls, tags: List[str]) -> List[str]:
        if len(tags) != 3:
            raise ValueError(f"Expected exactly 3 tags, got {len(tags)}")
        for t in tags:
            if not (3 <= len(t) <= 30):
                raise ValueError(f"Tag '{t}' must be 3-30 characters (got {len(t)})")
        return tags

    @field_validator("summary")
    @classmethod
    def summary_at_most_25_words(cls, summary: str) -> str:
        word_count = len(summary.split())
        if word_count > 25:
            raise ValueError(f"Summary must be at most 25 words (got {word_count})")
        return summary


def validate_planner_output(proposal: dict) -> str:
    """Returns an empty string if valid, else a human-readable error message
    suitable for feeding back into the Planner's retry prompt."""
    try:
        PlannerOutputSchema(**proposal)
        return ""
    except ValidationError as e:
        return "; ".join(err["msg"] for err in e.errors())

# Shared state

class AgentState(TypedDict):
    title: str
    content: str
    email: str
    strict: bool
    task: str
    turn_ceiling: int
    force_issues: bool  # test hook: makes the reviewer always report issues
    planner_proposal: Dict[str, Any]
    reviewer_feedback: Dict[str, Any]
    validation_error: str      # HW2 Part 4.1/4.2: schema validation feedback
    validation_retry_count: int
    turn_count: int
    final_output: Dict[str, Any]

# Helpers (shared with agents_demo.py's approach)

def extract_json(text: str) -> dict:
    """Best-effort extraction of a JSON object from an LLM response."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON object found in model output:\n{text}")
    return json.loads(match.group(0))


def finalize(reviewer_output: dict, planner_output: dict) -> dict:
    """Deterministic finalization: enforce 3-tag / 25-word constraints,
    backfilling from the Planner's tags if the Reviewer under-filled."""
    tags = list(dict.fromkeys(reviewer_output.get("tags", [])))
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

    return {"tags": tags, "summary": summary}

# Nodes

_client = ModelClient(temperature=0.7)


def planner_node(state: AgentState) -> Dict[str, Any]:
    """Planner agent: reads title/content (and, on a retry, the Reviewer's
    prior objection) and proposes 3 tags + a <=25-word summary."""
    print("---NODE: Planner ---")

    retry_note = ""
    if state.get("validation_error"):
    
        retry_note = (
            "\nYour previous response FAILED SCHEMA VALIDATION for this "
            f"reason: {state['validation_error']}\n"
            "Produce a corrected response that satisfies the schema exactly: "
            "exactly 3 tags, each 3-30 characters, and a summary of at most "
            "25 words."
        )
    elif state.get("reviewer_feedback"):
        retry_note = (
            "\nThe previous draft was rejected for this reason: "
            f"{state['reviewer_feedback'].get('review_notes', '')}\n"
            "Produce a corrected draft that fixes this."
        )

    prompt = f"""You are the PLANNER agent in a content-tagging pipeline.

Given the TITLE and CONTENT below, produce:
1. Exactly 3 short topical tags (2-3 words each) that best describe the
   specific content — derive them from what is actually written, do not
   invent generic categories that aren't supported by the text.
2. A one-sentence summary of at most 25 words.
{retry_note}
TITLE: {state['title']}
CONTENT: {state['content']}

Respond with ONLY a JSON object in this exact shape, no other text:
{{"tags": ["tag1", "tag2", "tag3"], "summary": "..."}}
"""
    result = _client.complete([{"role": "user", "content": prompt}])
    proposal = extract_json(result.content)

    # validate against the Pydantic schema. On failure,
    # record the error for the next retry instead of proceeding to Reviewer.
    error = validate_planner_output(proposal)
    prior_retries = state.get("validation_retry_count", 0)

    # Clear any stale reviewer feedback from a prior round so the router
    # sends this fresh proposal to the Reviewer again, instead of reusing
    # the old verdict and looping through the Planner repeatedly unreviewed.
    return {
        "planner_proposal": proposal,
        "reviewer_feedback": {},
        "validation_error": error,
        "validation_retry_count": prior_retries + 1 if error else prior_retries,
    }


def reviewer_node(state: AgentState) -> Dict[str, Any]:
    """Reviewer agent: critiques the Planner's draft against the source
    text and either approves it or flags issues to send back."""
    print("---NODE: Reviewer ---")

    if state.get("force_issues"):
        # Test hook for the self-correction loop (HW2 Part 3, Step 6):
        # forces a "has issues" verdict without an LLM call.
        return {
            "reviewer_feedback": {
                "tags": state["planner_proposal"].get("tags", []),
                "summary": state["planner_proposal"].get("summary", ""),
                "has_issues": True,
                "review_notes": "Forced issue for self-correction-loop testing.",
            }
        }

    prompt = f"""You are the REVIEWER agent in a content-tagging pipeline.

Original TITLE: {state['title']}
Original CONTENT: {state['content']}

The PLANNER produced this draft:
{json.dumps(state['planner_proposal'])}

Check the draft against the original text:
- Are all 3 tags actually supported by the content (not generic/invented)?
- Is the summary accurate and at most 25 words?
- Are there exactly 3 tags, no more, no fewer?

If the draft is good, return it unchanged with "has_issues": false. If not,
return corrected tags/summary with "has_issues": true. Respond with ONLY a
JSON object in this exact shape, no other text:
{{"tags": ["tag1", "tag2", "tag3"], "summary": "...", "has_issues": true/false, "review_notes": "one short sentence explaining what you checked or changed"}}
"""
    result = _client.complete([{"role": "user", "content": prompt}])
    feedback = extract_json(result.content)
    return {"reviewer_feedback": feedback}


def supervisor_node(state: AgentState) -> Dict[str, Any]:
    """State-updating node only: increments the turn counter."""
    return {"turn_count": state.get("turn_count", 0) + 1}

# Router (reads state, returns a string destination — no state mutation)

def router_logic(state: AgentState) -> str:
    ceiling = state.get("turn_ceiling", TURN_CEILING_DEFAULT)

    if state.get("turn_count", 0) >= ceiling:
        return END

    if not state.get("planner_proposal"):
        return "planner"

    # Schema validation failure (Part 4.2): retry the Planner directly,
    # skip the Reviewer until the shape is valid.
    if state.get("validation_error"):
        return "planner"

    feedback = state.get("reviewer_feedback")
    if not feedback:
        return "reviewer"

    if feedback.get("has_issues"):
        return "planner"

    return END

# Graph assembly
def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("supervisor", supervisor_node)
    graph.add_node("planner", planner_node)
    graph.add_node("reviewer", reviewer_node)

    graph.set_entry_point("supervisor")
    graph.add_conditional_edges(
        "supervisor",
        router_logic,
        {"planner": "planner", "reviewer": "reviewer", END: END},
    )
    graph.add_edge("planner", "supervisor")
    graph.add_edge("reviewer", "supervisor")

    return graph.compile()
# Runner

def run_once(title: str, content: str, turn_ceiling: int = TURN_CEILING_DEFAULT,
             force_issues: bool = False, verbose: bool = True) -> dict:
    app = build_graph()

    initial_state: AgentState = {
        "title": title,
        "content": content,
        "email": "",
        "strict": False,
        "task": "tag_and_summarize",
        "turn_ceiling": turn_ceiling,
        "force_issues": force_issues,
        "planner_proposal": {},
        "reviewer_feedback": {},
        "validation_error": "",
        "validation_retry_count": 0,
        "turn_count": 0,
        "final_output": {},
    }

    start = time.time()
    final_state = initial_state
    for step in app.stream(initial_state):
        node_name, update = next(iter(step.items()))
        final_state = {**final_state, **update}
        if verbose:
            print(f"\n--- after '{node_name}' (turn_count={final_state.get('turn_count')}) ---")
            if node_name == "planner":
                print(json.dumps(final_state["planner_proposal"], indent=2))
            if node_name == "reviewer":
                print(json.dumps(final_state["reviewer_feedback"], indent=2))

    latency_ms = (time.time() - start) * 1000

    schema_valid = not final_state.get("validation_error")
    reviewer_clean = (
        bool(final_state.get("reviewer_feedback"))
        and not final_state["reviewer_feedback"].get("has_issues")
    )
    succeeded = schema_valid and reviewer_clean

    if not succeeded:
        final = finalize(
            final_state.get("reviewer_feedback") or {},
            final_state.get("planner_proposal") or {},
        )
        outcome = "abandoned_at_ceiling"
    else:
        final = finalize(final_state["reviewer_feedback"], final_state["planner_proposal"])
        retries = final_state.get("validation_retry_count", 0)
        if retries == 0:
            outcome = "valid_first_attempt"
        elif retries == 1:
            outcome = "valid_after_1_retry"
        else:
            outcome = "valid_after_2plus_retries"

    if verbose:
        print("\n=== FINAL OUTPUT ===")
        print(json.dumps(final, indent=2))
        print(f"\n(turns: {final_state.get('turn_count')}, "
              f"validation_retries: {final_state.get('validation_retry_count', 0)}, "
              f"outcome: {outcome}, latency: {latency_ms:.0f} ms)")

    return {
        "final": final,
        "turn_count": final_state.get("turn_count", 0),
        "validation_retry_count": final_state.get("validation_retry_count", 0),
        "outcome": outcome,
        "latency_ms": latency_ms,
    }


def main():
    parser = argparse.ArgumentParser(description="Stateful Planner/Reviewer/Supervisor graph")
    parser.add_argument("--title", type=str)
    parser.add_argument("--content", type=str)
    parser.add_argument("--input-file", type=str)
    parser.add_argument("--turn-ceiling", type=int, default=TURN_CEILING_DEFAULT)
    parser.add_argument("--force-issues", action="store_true",
                         help="Force the Reviewer to always report issues, to test the self-correction loop")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    if args.input_file:
        with open(args.input_file, "r") as f:
            data = json.load(f)
        title, content = data["title"], data["content"]
    elif args.title and args.content:
        title, content = args.title, args.content
    else:
        title = "Line 22 - Bus stalled on Main St"
        content = (
            "The 8:15 AM bus on Route 22 broke down near the Main St and "
            "5th Ave intersection. Passengers were stranded for 20 minutes "
            "before a replacement vehicle arrived. Driver reported a "
            "mechanical issue with the engine."
        )

    run_once(title, content, args.turn_ceiling, args.force_issues, verbose=not args.quiet)


if __name__ == "__main__":
    main()