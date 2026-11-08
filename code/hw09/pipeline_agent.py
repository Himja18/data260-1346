"""The HW8 agent pipeline as the cache-miss path: question -> s1346_inbox ... s1346_final -> answer.

Planner, Writer and Reviewer (qwen2.5:3b through src/model_client.py) must be running, exactly as in HW8:
    python code/kafka_agents/planner.py  |  writer.py  |  reviewer.py
"""
import sys
import time
import uuid
from typing import Any

import hw09_config as cfg

sys.path.insert(0, str(cfg.CODE_DIR))


class AgentTimeout(RuntimeError):
    """No final answer on s1346_final in time."""


class KafkaPipelineAgent:
    """Send one question to the HW8 pipeline and wait for its final answer (matched by correlation_id)."""

    name = "HW8 Kafka pipeline (Planner -> Writer -> Reviewer, qwen2.5:3b)"

    def __init__(self, log: Any, timeout_s: float = cfg.AGENT_TIMEOUT_S) -> None:
        from confluent_kafka import Consumer

        import hw08_config as cfg8
        from kafka_common import assign_at_end, make_producer
        self.cfg8 = cfg8
        self.log = log
        self.timeout_s = timeout_s
        self.reader = Consumer({"bootstrap.servers": cfg8.KAFKA_BOOTSTRAP, "enable.auto.commit": False,
                                "group.id": f"{cfg.PREFIX}_hw09_cache_{uuid.uuid4().hex[:8]}"})
        assign_at_end(self.reader, cfg8.FINAL_TOPIC)     # only finals produced from now on
        self.producer = make_producer(f"{cfg.PREFIX}-hw09-cache")
        self.early: dict[str, dict] = {}                 # finals for other ids that arrived while waiting

    def ask(self, question: str) -> dict:
        """Returns {answer, status, correlation_id, agent_ms}."""
        from kafka_common import decode, encode, new_correlation_id, now_iso, trace
        corr = new_correlation_id()
        msg = {"correlation_id": corr, "question": question, "asked_by": cfg.STUDENT_NAME, "sent_at": now_iso(),
               "trace": [{"stage": "hw09_cache_miss", "instance": "semantic_cache", "at": now_iso()}]}
        started = time.perf_counter()
        self.producer.produce(self.cfg8.INBOX_TOPIC, key=corr.encode(), value=encode(msg))
        self.producer.flush(10)
        trace("hw09_cache", "agent_sent", corr, topic=self.cfg8.INBOX_TOPIC)
        self.log.info("   agent: SENT -> %s corr=%s (waiting for %s)", self.cfg8.INBOX_TOPIC, corr[:8],
                      self.cfg8.FINAL_TOPIC)
        final = self.early.pop(corr, None)
        while final is None and time.perf_counter() - started < self.timeout_s:
            m = self.reader.poll(1.0)
            if m is None or m.error():
                continue
            try:
                value = decode(m.value())
            except ValueError:
                continue
            if not isinstance(value, dict):
                continue
            if value.get("correlation_id") == corr:
                final = value
            elif value.get("correlation_id"):
                self.early[value["correlation_id"]] = value
        if final is None:
            raise AgentTimeout(f"no final answer for {corr} within {self.timeout_s:.0f}s - "
                               "are planner.py, writer.py and reviewer.py running?")
        ms = (time.perf_counter() - started) * 1000
        trace("hw09_cache", "agent_received", corr, topic=self.cfg8.FINAL_TOPIC)
        return {"answer": str(final.get("answer", "")).strip(), "status": final.get("status"),
                "correlation_id": corr, "agent_ms": round(ms, 1)}

    def close(self) -> None:
        """Release the Kafka consumer."""
        self.reader.close()


class FakeAgent:
    """Offline tests only: deterministic answer, fixed simulated latency."""

    name = "fake agent (offline tests)"

    def __init__(self, delay_s: float = 0.05) -> None:
        self.delay_s = delay_s
        self.calls = 0

    def ask(self, question: str) -> dict:
        """Echo the facts back as the 'answer'."""
        self.calls += 1
        time.sleep(self.delay_s)
        return {"answer": f"[fake answer #{self.calls}] {question}", "status": "approved",
                "correlation_id": f"fake-{self.calls}", "agent_ms": self.delay_s * 1000}

    def close(self) -> None:
        """Nothing to release."""
