"""HW8 Part 2 - Writer agent: s1346_tasks (plan) -> s1346_drafts (draft answer).

    python code/kafka_agents/writer.py                     # normal: idempotent, manual commit, retries + DLQ
    python code/kafka_agents/writer.py --instance-id 2     # a second instance in the same consumer group
    python code/kafka_agents/writer.py --fake-llm          # deterministic draft, no model

s1346_tasks has two partitions, so two Writer instances in group s1346_writers share the work.
Part 3 "ordering probe" messages (kind=ordering_probe) are only recorded, not forwarded.
"""
import sys
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import hw08_config as cfg  # noqa: E402
from agent_base import KafkaAgent, common_args, make_model  # noqa: E402

SYSTEM = ("You are the WRITER agent of a Municipal Transit Incidents help desk. Incident categories are exactly "
          "Delay, Breakdown, Accident and Service Change. Write a clear answer for a rider in at most 120 words, "
          "following the plan. Plain text only.")

TASK_FIELDS = ("correlation_id", "question", "plan")
PROBE_FIELDS = ("correlation_id", "entity_id", "seq")


def required_for(preview: Any) -> tuple[str, ...]:
    """Ordering probes need entity_id/seq; normal tasks need question/plan."""
    if isinstance(preview, dict) and preview.get("kind") == "ordering_probe":
        return PROBE_FIELDS
    return TASK_FIELDS


def build_handler(model: Any):  # noqa: ANN201
    """Return the writer's message handler."""

    def handle(msg: dict) -> Optional[dict]:
        if msg.get("kind") == "ordering_probe":
            return None                       # Part 3 IV: processing order is recorded by the agent loop
        plan = msg["plan"] if isinstance(msg["plan"], list) else [str(msg["plan"])]
        if model is not None:
            reply = model.complete([
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": f"Question: {msg['question']}\nPlan:\n"
                                            + "\n".join(f"- {s}" for s in plan)}])
            draft, source = reply.content.strip(), cfg.MODEL_NAME
        else:
            draft = (f"To answer '{msg['question']}': " + " ".join(f"({i}) {s}." for i, s in enumerate(plan, 1)))
            source = "template"
        if not draft:
            raise ValueError("writer produced an empty draft")
        return {"correlation_id": msg["correlation_id"], "question": msg["question"], "plan": plan,
                "draft": draft, "written_by": source, "trace": list(msg.get("trace", []))}

    return handle


def main() -> None:
    """Start one writer instance."""
    args = common_args(__doc__).parse_args()
    agent = KafkaAgent("writer", cfg.TASKS_TOPIC, cfg.DRAFTS_TOPIC, cfg.WRITER_GROUP,
                       build_handler(make_model(args.fake_llm)), TASK_FIELDS, args, required_for=required_for)
    agent.run()


if __name__ == "__main__":
    main()
