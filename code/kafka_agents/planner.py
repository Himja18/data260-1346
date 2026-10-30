"""HW8 Part 2 - Planner agent: s1346_inbox (question) -> s1346_tasks (plan).

    python code/kafka_agents/planner.py            # qwen2.5:3b via Ollama
    python code/kafka_agents/planner.py --fake-llm # deterministic plan, no model
"""
import re
import sys
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import hw08_config as cfg  # noqa: E402
from agent_base import KafkaAgent, common_args, extract_json, make_model  # noqa: E402

SYSTEM = ("You are the PLANNER agent of a Municipal Transit Incidents help desk. Incident categories are exactly "
          "Delay, Breakdown, Accident and Service Change. Break the rider's question into 3 or 4 concrete steps "
          "that the WRITER agent must cover in its answer. Each step is a short instruction of 5-15 words about "
          "THIS question (mention the route, category or action), never a placeholder like 'Step 1'.\n"
          "Example for 'The 14 bus skipped my stop twice, what can I do?':\n"
          '{"steps": ["Classify the skipped stops as a Delay or Service Change incident", '
          '"Explain how to report it with route 14, stop name and times", '
          '"Say what the transit agency does after a report"]}\n'
          'Reply with ONLY a JSON object of the form {"steps": [...]}.')
PLACEHOLDER = re.compile(r"^(step\s*\d+|\.\.\.|todo|n/?a)[.:]?$", re.IGNORECASE)


def clean_steps(raw: Any) -> list[str]:
    """Keep real steps only: drop placeholders like 'Step 1' and fragments under 12 characters."""
    steps = [str(s).strip() for s in (raw if isinstance(raw, list) else [])]
    return [s for s in steps if len(s) >= 12 and not PLACEHOLDER.match(s)][:4]


def fallback_steps(question: str) -> list[str]:
    """Domain plan used when the model gives no usable steps."""
    q = question.lower()
    category = next((c for c in cfg.CATEGORIES if c.lower() in q), None) or (
        "Breakdown" if "broke" in q else "Accident" if "crash" in q or "collision" in q else
        "Delay" if "wait" in q or "late" in q else "Service Change")
    return [f"Classify the incident as {category} and explain why",
            "Explain how to report it: route, location, time and what happened",
            "Say what happens after the report and how long it usually takes"]


def build_handler(model: Any):  # noqa: ANN201
    """Return the planner's message handler."""

    def handle(msg: dict) -> Optional[dict]:
        question = str(msg["question"]).strip()
        steps: list[str] = []
        source = "template"
        if model is not None:
            messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": f"Question: {question}"}]
            for _attempt in range(2):            # one retry if the model returns placeholders
                reply = model.complete(messages)
                steps = clean_steps((extract_json(reply.content) or {}).get("steps"))
                if len(steps) >= 2:
                    source = cfg.MODEL_NAME
                    break
                messages += [{"role": "assistant", "content": reply.content},
                             {"role": "user", "content": "Those are not usable steps. Write 3 concrete steps "
                                                         "about this exact question, as JSON."}]
        if len(steps) < 2:
            steps, source = fallback_steps(question), "template (model gave no usable steps)"
        return {"correlation_id": msg["correlation_id"], "question": question, "plan": steps,
                "planned_by": source, "asked_by": msg.get("asked_by"), "trace": list(msg.get("trace", []))}

    return handle


def main() -> None:
    """Start the planner."""
    args = common_args(__doc__).parse_args()
    agent = KafkaAgent("planner", cfg.INBOX_TOPIC, cfg.TASKS_TOPIC, cfg.PLANNER_GROUP,
                       build_handler(make_model(args.fake_llm)), ("correlation_id", "question"), args)
    agent.run()


if __name__ == "__main__":
    main()
