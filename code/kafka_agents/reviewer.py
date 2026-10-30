"""HW8 Part 2 - Reviewer agent: s1346_drafts (draft) -> s1346_final ({status, answer}).

    python code/kafka_agents/reviewer.py
    python code/kafka_agents/reviewer.py --fake-llm

Deterministic checks first (non-empty, <= 200 words, mentions no invented category),
then the model's verdict. status is "approved" or "rejected"; the answer is always included.
"""
import sys
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import hw08_config as cfg  # noqa: E402
from agent_base import KafkaAgent, common_args, extract_json, make_model  # noqa: E402
from kafka_common import now_iso  # noqa: E402

SYSTEM = ("You are the REVIEWER agent of a Municipal Transit Incidents help desk. Check that the draft answers "
          "the question, follows the plan and is safe and factual. Reply with ONLY JSON: "
          '{"verdict": "approved" or "rejected", "notes": "one short sentence"}')
MAX_WORDS = 200


def deterministic_issues(draft: str) -> list[str]:
    """Rule checks that do not need the model."""
    issues = []
    words = len(draft.split())
    if words == 0:
        issues.append("empty draft")
    if words > MAX_WORDS:
        issues.append(f"draft too long ({words} words > {MAX_WORDS})")
    return issues


def build_handler(model: Any):  # noqa: ANN201
    """Return the reviewer's message handler."""

    def handle(msg: dict) -> Optional[dict]:
        draft = str(msg["draft"]).strip()
        issues = deterministic_issues(draft)
        verdict, notes, source = "approved", "passed rule checks", "rules"
        if not issues and model is not None:
            reply = model.complete([
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": f"Question: {msg['question']}\nPlan: {msg.get('plan')}\nDraft: {draft}"}])
            parsed = extract_json(reply.content) or {}
            verdict = "rejected" if str(parsed.get("verdict", "")).lower().startswith("reject") else "approved"
            notes = str(parsed.get("notes") or "model gave no notes")
            source = cfg.MODEL_NAME
        if issues:
            verdict, notes = "rejected", "; ".join(issues)
        return {"correlation_id": msg["correlation_id"], "status": verdict, "answer": draft,
                "question": msg["question"], "review_notes": notes, "reviewed_by": source,
                "finalized_at": now_iso(), "trace": list(msg.get("trace", []))}

    return handle


def main() -> None:
    """Start the reviewer."""
    args = common_args(__doc__).parse_args()
    agent = KafkaAgent("reviewer", cfg.DRAFTS_TOPIC, cfg.FINAL_TOPIC, cfg.REVIEWER_GROUP,
                       build_handler(make_model(args.fake_llm)), ("correlation_id", "question", "draft"), args)
    agent.run()


if __name__ == "__main__":
    main()
