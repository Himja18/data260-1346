"""HW8 Kafka helpers shared by the worker, the client, the API wrapper, the agents and the runners.

- logging that shows the student name on every console line and appends to reports/hw08/RUN_LOG.txt
- a structured trace (reports/hw08/raw/message_trace.jsonl) of every send/receive/reply event
- producer/consumer factories (manual offset commit by default)
- small admin helpers: wait for the broker, check topics, committed offsets, "start at the end" consumers
"""
import json
import logging
import os
import sys
import time
import uuid
from datetime import datetime
from typing import Any, Optional

from confluent_kafka import Consumer, KafkaException, Producer, TopicPartition
from confluent_kafka.admin import AdminClient

import hw08_config as cfg

_LOG_FORMAT = f"%(asctime)s.%(msecs)03d | {cfg.STUDENT_NAME} | {cfg.PREFIX} | %(name)-14s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(component: str, to_run_log: bool = True) -> logging.Logger:
    """Return a logger that prints to stdout and (by default) appends to reports/hw08/RUN_LOG.txt."""
    cfg.ensure_dirs()
    logger = logging.getLogger(component)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter(_LOG_FORMAT, _DATE_FORMAT)
    out = logging.StreamHandler(sys.stdout)
    out.setFormatter(fmt)
    logger.addHandler(out)
    if to_run_log and os.getenv("HW08_RUN_LOG", "1") != "0":
        fh = logging.FileHandler(cfg.RUN_LOG, encoding="utf-8")     # append mode; O_APPEND is safe across processes
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    logger.propagate = False
    return logger


def now_iso() -> str:
    """Local timestamp with UTC offset and millisecond precision."""
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def new_correlation_id() -> str:
    """Create a correlation id once, on the client side."""
    return str(uuid.uuid4())


def trace(component: str, event: str, correlation_id: Optional[str], **fields: Any) -> None:
    """Append one structured event to the shared message trace (used to print the full sequence)."""
    cfg.ensure_dirs()
    rec = {"ts": time.time(), "at": now_iso(), "component": component, "event": event,
           "correlation_id": correlation_id, **fields}
    with open(cfg.TRACE_FILE, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, default=str) + "\n")


def encode(obj: Any) -> bytes:
    """JSON-encode a message value."""
    return json.dumps(obj, default=str).encode("utf-8")


def decode(raw: Optional[bytes]) -> Any:
    """JSON-decode a message value (raises ValueError on bad JSON / bad UTF-8)."""
    if raw is None:
        raise ValueError("message has no value")
    return json.loads(raw.decode("utf-8"))


def short(obj: Any, limit: int = 400) -> str:
    """Compact JSON for log lines."""
    text = json.dumps(obj, default=str, ensure_ascii=False)
    return text if len(text) <= limit else text[:limit] + "...}"


def make_producer(client_id: str, **overrides: Any) -> Producer:
    """Idempotent, acks=all producer."""
    conf = {"bootstrap.servers": cfg.KAFKA_BOOTSTRAP, "client.id": client_id,
            "acks": "all", "enable.idempotence": True, "linger.ms": 5}
    conf.update(overrides)
    return Producer(conf)


def make_consumer(group_id: str, client_id: str, auto_commit: bool = False,
                  offset_reset: str = "earliest", **overrides: Any) -> Consumer:
    """Group consumer. auto_commit=False (default) means the caller commits after successful processing."""
    conf = {"bootstrap.servers": cfg.KAFKA_BOOTSTRAP, "group.id": group_id, "client.id": client_id,
            "auto.offset.reset": offset_reset, "enable.auto.commit": auto_commit,
            "session.timeout.ms": 10000, "heartbeat.interval.ms": 1000,
            "max.poll.interval.ms": 300000}
    if auto_commit:
        conf["auto.commit.interval.ms"] = 200      # the "before fix" setting: commit soon after poll
    conf.update(overrides)
    return Consumer(conf)


def admin() -> AdminClient:
    """Admin client for metadata queries."""
    return AdminClient({"bootstrap.servers": cfg.KAFKA_BOOTSTRAP})


def wait_for_broker(logger: Optional[logging.Logger] = None, timeout_s: float = 90) -> None:
    """Block until the broker answers a metadata request (containers can start before Kafka is ready)."""
    deadline = time.time() + timeout_s
    last: Exception | None = None
    while time.time() < deadline:
        try:
            admin().list_topics(timeout=5)
            return
        except KafkaException as exc:
            last = exc
            if logger:
                logger.info("waiting for Kafka at %s ...", cfg.KAFKA_BOOTSTRAP)
            time.sleep(2)
    raise RuntimeError(f"Kafka not reachable at {cfg.KAFKA_BOOTSTRAP}: {last}")


def topic_partitions() -> dict[str, int]:
    """Existing topics -> partition count."""
    md = admin().list_topics(timeout=10)
    return {name: len(t.partitions) for name, t in md.topics.items() if not name.startswith("__")}


def require_topics(names: list[str], logger: logging.Logger, wait_s: float = 0) -> None:
    """Wait up to wait_s for the topics (created with the Kafka CLI), then exit with a clear message."""
    deadline = time.time() + wait_s
    while True:
        existing = topic_partitions()
        missing = [n for n in names if n not in existing]
        if not missing:
            return
        if time.time() >= deadline:
            logger.error("missing topics %s - create them first: make hw08-topics", missing)
            raise SystemExit(2)
        logger.info("waiting for topics %s (run: make hw08-topics) ...", missing)
        time.sleep(5)


def assign_at_end(consumer: Consumer, topic: str) -> None:
    """Assign every partition of `topic` at its current end, so only messages sent after this call are read."""
    md = consumer.list_topics(topic, timeout=10)
    parts = []
    for p in md.topics[topic].partitions:
        _low, high = consumer.get_watermark_offsets(TopicPartition(topic, p), timeout=10)
        parts.append(TopicPartition(topic, p, high))
    consumer.assign(parts)


def end_offsets(topic: str) -> dict[int, int]:
    """Partition -> high watermark."""
    c = Consumer({"bootstrap.servers": cfg.KAFKA_BOOTSTRAP, "group.id": f"{cfg.PREFIX}_probe_{uuid.uuid4().hex[:6]}",
                  "enable.auto.commit": False})
    try:
        md = c.list_topics(topic, timeout=10)
        return {p: c.get_watermark_offsets(TopicPartition(topic, p), timeout=10)[1]
                for p in md.topics[topic].partitions}
    finally:
        c.close()


def committed_offsets(group_id: str, topic: str) -> dict[int, int]:
    """Partition -> committed offset of a consumer group (-1001 = nothing committed)."""
    c = Consumer({"bootstrap.servers": cfg.KAFKA_BOOTSTRAP, "group.id": group_id, "enable.auto.commit": False})
    try:
        md = c.list_topics(topic, timeout=10)
        tps = [TopicPartition(topic, p) for p in md.topics[topic].partitions]
        return {tp.partition: tp.offset for tp in c.committed(tps, timeout=10)}
    finally:
        c.close()


def set_group_to_end(group_id: str, topic: str) -> dict[int, int]:
    """Commit the current end offsets for a (new) group, so its first consumer starts with fresh messages only."""
    ends = end_offsets(topic)
    c = Consumer({"bootstrap.servers": cfg.KAFKA_BOOTSTRAP, "group.id": group_id, "enable.auto.commit": False})
    try:
        c.commit(offsets=[TopicPartition(topic, p, o) for p, o in ends.items()], asynchronous=False)
    finally:
        c.close()
    return ends


def read_topic(topic: str, start: Optional[dict[int, int]] = None, idle_s: float = 3.0,
               max_s: float = 30.0) -> list[dict]:
    """Read a topic (from `start` offsets or the beginning) until idle; returns decoded records with metadata."""
    c = Consumer({"bootstrap.servers": cfg.KAFKA_BOOTSTRAP, "group.id": f"{cfg.PREFIX}_reader_{uuid.uuid4().hex[:6]}",
                  "enable.auto.commit": False, "auto.offset.reset": "earliest"})
    out: list[dict] = []
    try:
        md = c.list_topics(topic, timeout=10)
        parts = []
        for p in md.topics[topic].partitions:
            low, _high = c.get_watermark_offsets(TopicPartition(topic, p), timeout=10)
            parts.append(TopicPartition(topic, p, (start or {}).get(p, low)))
        c.assign(parts)
        deadline, last = time.time() + max_s, time.time()
        while time.time() < deadline and time.time() - last < idle_s:
            msg = c.poll(0.5)
            if msg is None or msg.error():
                continue
            last = time.time()
            try:
                value: Any = decode(msg.value())
            except ValueError:
                value = (msg.value() or b"").decode("utf-8", "replace")
            out.append({"partition": msg.partition(), "offset": msg.offset(),
                        "key": msg.key().decode() if msg.key() else None, "value": value})
    finally:
        c.close()
    return out
