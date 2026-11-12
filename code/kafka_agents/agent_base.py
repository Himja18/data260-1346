"""HW8 Parts 2-3 - shared consume -> process -> produce -> commit loop for Planner, Writer and Reviewer.

Agents never call each other: each one reads its input topic and writes its output topic.
The loop holds all of the Part 3 failure handling, switchable per flag so the
"before fix" behaviour can be shown with the same code:

  idempotency  - a correlation_id already processed by this agent is skipped (no second output).
                 The processed set is persisted in data/hw08/<agent>_processed.json, so it survives restarts.
                 --no-idempotency turns it off.
  offset commit - manual commit only after the output was delivered (flush) and the state saved.
                 --auto-commit switches to Kafka auto-commit (offset committed soon after poll).
  poison       - each message gets MAX_ATTEMPTS tries with backoff, then goes to s1346_dead_letter
                 and its offset is committed so later messages are not blocked.
                 --no-dlq: no retries/DLQ, the agent crashes on a bad message (and does so again on restart).
"""
import argparse
import json
import os
import signal
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Optional

sys.path[:0] = [str(Path(__file__).resolve().parents[1]), str(Path(__file__).resolve().parents[2] / "src")]

from confluent_kafka import KafkaException  # noqa: E402

import hw08_config as cfg  # noqa: E402
from kafka_common import (  # noqa: E402
    decode,
    encode,
    make_consumer,
    make_producer,
    now_iso,
    require_topics,
    setup_logging,
    short,
    trace,
    wait_for_broker,
)
from tracing import queue_span, write_span  # noqa: E402  (HW10 Part 4 spans)


class PoisonMessageError(ValueError):
    """The message can never be processed (bad JSON, missing fields)."""


def common_args(description: str) -> argparse.ArgumentParser:
    """CLI flags shared by all three agents."""
    ap = argparse.ArgumentParser(description=description)
    ap.add_argument("--instance-id", default=os.getenv("AGENT_INSTANCE", "1"))
    ap.add_argument("--group", default=None, help="consumer group (default: the agent's group from hw08_config)")
    ap.add_argument("--fake-llm", action="store_true", help="deterministic template output instead of Ollama")
    ap.add_argument("--no-idempotency", action="store_true", help="before-fix: replays produce a second output")
    ap.add_argument("--auto-commit", action="store_true", help="before-fix: offsets auto-committed after poll")
    ap.add_argument("--no-dlq", action="store_true", help="before-fix: no retries/dead-letter, crash on poison")
    ap.add_argument("--max-attempts", type=int, default=cfg.MAX_ATTEMPTS)
    ap.add_argument("--work-delay", type=float, default=0.0, help="extra seconds of simulated work per message")
    ap.add_argument("--state-file", default=None, help="idempotency store (default data/hw08/<agent>_processed.json)")
    ap.add_argument("--events-file", default=None, help="append one JSON line per processed message (Part 3 runs)")
    return ap


class ProcessedStore:
    """Persistent set of processed keys (JSON file, atomic rewrite)."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.keys: set[str] = set()
        if path.exists():
            try:
                self.keys = set(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                self.keys = set()

    def __contains__(self, key: str) -> bool:
        return key in self.keys

    def add(self, key: str) -> None:
        """Record a key and persist it."""
        self.keys.add(key)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(sorted(self.keys)), encoding="utf-8")
        os.replace(tmp, self.path)


def require_fields(value: Any, fields: tuple[str, ...]) -> dict:
    """Raise PoisonMessageError unless value is a dict with every field present and non-empty."""
    if not isinstance(value, dict):
        raise PoisonMessageError("message is not a JSON object")
    missing = [f for f in fields if value.get(f) in (None, "", [], {})]
    if missing:
        raise PoisonMessageError(f"missing required field(s): {', '.join(missing)}")
    return value


def process_with_retries(raw: Optional[bytes], handler: Callable[[dict], Optional[dict]],
                         required: tuple[str, ...], max_attempts: int, log: Any,
                         sleep: Callable[[float], None] = time.sleep) -> tuple[Optional[dict], Optional[str], int, Any]:
    """Try decode+validate+handle up to max_attempts times.

    Returns (output, error, attempts, decoded_value). output is None with error set when every attempt failed.
    """
    error, value = None, None
    for attempt in range(1, max_attempts + 1):
        try:
            try:
                value = decode(raw)
            except ValueError as exc:
                raise PoisonMessageError(f"invalid JSON: {exc}") from exc
            require_fields(value, required)
            return handler(value), None, attempt, value
        except Exception as exc:                                        # noqa: BLE001 - any failure is retried
            error = f"{exc.__class__.__name__}: {exc}"
            log.warning("RETRY attempt %d/%d failed: %s", attempt, max_attempts, error)
            if attempt < max_attempts:
                sleep(cfg.RETRY_BACKOFF_S[min(attempt - 1, len(cfg.RETRY_BACKOFF_S) - 1)])
    return None, error, max_attempts, value


class KafkaAgent:
    """One pipeline stage: in_topic -> handler -> out_topic."""

    def __init__(self, name: str, in_topic: str, out_topic: str, group: str,
                 handler: Callable[[dict], Optional[dict]], required: tuple[str, ...], args: argparse.Namespace,
                 required_for: Optional[Callable[[Any], tuple[str, ...]]] = None) -> None:
        self.name, self.in_topic, self.out_topic = name, in_topic, out_topic
        self.instance = f"{name}-{args.instance_id}"
        self.group = args.group or group
        self.handler, self.required, self.args = handler, required, args
        self.required_for = required_for
        self.log = setup_logging(self.instance)
        state = Path(args.state_file) if args.state_file else cfg.STATE_DIR / f"{name}_processed.json"
        self.store = ProcessedStore(state)
        self.running = True

    def _event(self, **fields: Any) -> None:
        """Append one processing record to --events-file (used by the Part 3 runner)."""
        if not self.args.events_file:
            return
        rec = {"ts": time.time(), "at": now_iso(), "instance": self.instance, "pid": os.getpid(), **fields}
        with open(self.args.events_file, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, default=str) + "\n")

    def run(self) -> None:
        """Main loop."""
        a = self.args
        wait_for_broker(self.log)
        require_topics([self.in_topic, self.out_topic, cfg.DEAD_LETTER_TOPIC], self.log)
        producer = make_producer(f"{cfg.PREFIX}-{self.instance}")
        consumer = make_consumer(self.group, f"{cfg.PREFIX}-{self.instance}", auto_commit=a.auto_commit)

        def on_assign(_c, parts) -> None:  # noqa: ANN001
            names = [f"{p.topic}[{p.partition}]" for p in parts]
            self.log.info("partitions assigned: %s", names)
            self._event(event="assigned", partitions=[p.partition for p in parts])

        def on_revoke(_c, parts) -> None:  # noqa: ANN001
            self.log.info("partitions revoked: %s", [f"{p.topic}[{p.partition}]" for p in parts])

        consumer.subscribe([self.in_topic], on_assign=on_assign, on_revoke=on_revoke)
        signal.signal(signal.SIGTERM, lambda *_: setattr(self, "running", False))
        self.log.info("%s ready: %s -> %s | group=%s | idempotency=%s | commit=%s | poison=%s | pid=%d",
                      self.instance, self.in_topic, self.out_topic, self.group,
                      "OFF" if a.no_idempotency else "on", "AUTO" if a.auto_commit else "manual-after-success",
                      "crash (no DLQ)" if a.no_dlq else f"{a.max_attempts} attempts -> {cfg.DEAD_LETTER_TOPIC}",
                      os.getpid())
        try:
            while self.running:
                msg = consumer.poll(1.0)
                if msg is None:
                    continue
                if msg.error():
                    self.log.warning("consumer error: %s", msg.error())
                    continue
                self._handle_message(msg, consumer, producer)
        except KeyboardInterrupt:
            pass
        finally:
            self.log.info("%s stopping", self.instance)
            consumer.close()

    def _handle_message(self, msg: Any, consumer: Any, producer: Any) -> None:
        """Process one record with idempotency, retries/DLQ and commit-after-success."""
        a = self.args
        t_recv = time.time()                                   # HW10: stage span starts at receive
        where = f"{msg.topic()}[{msg.partition()}]@{msg.offset()}"
        try:
            preview = decode(msg.value())
        except ValueError:
            preview = (msg.value() or b"")[:120].decode("utf-8", "replace")
        corr = preview.get("correlation_id") if isinstance(preview, dict) else None
        self.log.info("RECEIVED <- %s key=%s corr=%s", where, msg.key().decode() if msg.key() else None, corr)
        trace(self.instance, "agent_received", corr, topic=msg.topic(), partition=msg.partition(), offset=msg.offset())
        self._event(event="received", partition=msg.partition(), offset=msg.offset(), correlation_id=corr)

        if not a.no_idempotency and corr and corr in self.store:
            self.log.info("DUPLICATE corr=%s already processed by %s -> skipped, no new output; commit %s",
                          corr, self.name, where)
            self._event(event="duplicate_skipped", partition=msg.partition(), offset=msg.offset(), correlation_id=corr)
            if not a.auto_commit:
                consumer.commit(message=msg, asynchronous=False)
            return

        queue_span(corr, msg.topic(), msg.timestamp(), t_recv, self.instance, partition=msg.partition(),
                   offset=msg.offset())
        required = self.required_for(preview) if self.required_for else self.required
        if a.no_dlq:
            # before fix: one attempt, any failure crashes the agent without committing the offset
            try:
                value = decode(msg.value())
                require_fields(value, required)
                output = self._work(value)
            except Exception as exc:                                    # noqa: BLE001
                self.log.error("CRASH on %s: %s: %s - offset NOT committed, agent exits", where,
                               exc.__class__.__name__, exc)
                self._event(event="crash", partition=msg.partition(), offset=msg.offset(), error=str(exc))
                raise SystemExit(3) from exc
            attempts, error = 1, None
        else:
            output, error, attempts, value = process_with_retries(msg.value(), self._work, required,
                                                                  a.max_attempts, self.log)
            if error is not None:
                dead = {"source_agent": self.instance, "topic": msg.topic(), "partition": msg.partition(),
                        "offset": msg.offset(), "correlation_id": corr, "error": error, "attempts": attempts,
                        "raw_value": (msg.value() or b"").decode("utf-8", "replace"), "failed_at": now_iso()}
                producer.produce(cfg.DEAD_LETTER_TOPIC, key=(corr or where).encode(), value=encode(dead))
                producer.flush(10)
                self.log.error("DEAD-LETTER %s after %d attempts (%s) -> %s; offset committed, moving on",
                               where, attempts, error, cfg.DEAD_LETTER_TOPIC)
                trace(self.instance, "agent_dead_lettered", corr, topic=cfg.DEAD_LETTER_TOPIC, error=error)
                write_span(corr, self.name, t_recv, time.time(), "error", self.instance, error=error,
                           attempts=attempts, dead_letter_topic=cfg.DEAD_LETTER_TOPIC)
                self._event(event="dead_lettered", partition=msg.partition(), offset=msg.offset(),
                            correlation_id=corr, attempts=attempts, error=error)
                if not a.auto_commit:
                    consumer.commit(message=msg, asynchronous=False)
                return

        if output is not None:
            producer.produce(self.out_topic, key=str(output.get("correlation_id") or corr or "").encode() or None,
                             value=encode(output))
            producer.flush(10)
            self.log.info("SENT -> %s corr=%s message=%s", self.out_topic, corr, short(output, 300))
            trace(self.instance, "agent_sent", corr, topic=self.out_topic)
            write_span(corr, self.name, t_recv, time.time(), "ok", self.instance, attempts=attempts,
                       out_topic=self.out_topic)
        if corr and not a.no_idempotency:
            self.store.add(corr)
        if not a.auto_commit:
            try:
                consumer.commit(message=msg, asynchronous=False)
                self.log.info("COMMITTED %s (next offset %d) after successful processing", where, msg.offset() + 1)
            except KafkaException as exc:   # HW9: group rebalanced under load - keep running, do not crash
                self.log.warning("COMMIT FAILED %s (%s) - partition was reassigned; the message may be "
                                 "redelivered and the idempotency store will drop the duplicate", where, exc)
        self._event(event="processed", partition=msg.partition(), offset=msg.offset(), correlation_id=corr,
                    attempts=attempts, entity_id=value.get("entity_id") if isinstance(value, dict) else None,
                    seq=value.get("seq") if isinstance(value, dict) else None,
                    msg_index=value.get("msg_index") if isinstance(value, dict) else None,
                    produced=output is not None)

    def _work(self, value: dict) -> Optional[dict]:
        """Run the stage handler, with optional simulated work time (Part 3 consumer-death / ordering runs)."""
        delay = self.args.work_delay + float(value.get("work_ms", 0)) / 1000.0
        if delay > 0:
            self.log.info("processing corr=%s (work %.2fs) ...", value.get("correlation_id"), delay)
            time.sleep(delay)
        fault = value.get("inject_fault")
        if fault == self.name:        # HW10 Part 4.2: deliberate, documented failure for the failed-trace example
            raise RuntimeError(f"injected fault in {self.name} (inject_fault={fault!r})")
        out = self.handler(value)
        if out is not None and fault:
            out.setdefault("inject_fault", fault)                # carry it to the next stage
        if out is not None:
            out.setdefault("trace", list(value.get("trace", [])))
            out["trace"].append({"stage": self.name, "instance": self.instance, "at": now_iso()})
        return out


def extract_json(text: str) -> Optional[dict]:
    """First JSON object in a model reply, or None."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        obj = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def make_model(fake: bool) -> Any:
    """ModelClient (qwen2.5:3b via Ollama) or None in --fake-llm mode."""
    if fake:
        return None
    from model_client import ModelClient
    return ModelClient(model=cfg.MODEL_NAME, temperature=0.3, seed=cfg.SEED, num_predict=350, timeout_s=180)
