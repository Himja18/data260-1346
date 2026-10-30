"""HW8 Part 1 - Kafka request/response client for the Incident service.

The client creates the correlation_id once, sends the request to s1346_incident_requests with
reply_to = s1346_incident_responses, and waits for the response that echoes the same correlation_id.
A background thread reads the response topic and hands each response to the waiting caller,
so the FastAPI wrapper can serve concurrent requests with one client.
"""
import threading
import time
import uuid
from typing import Any, Optional

from confluent_kafka import Consumer

import hw08_config as cfg
from kafka_common import (
    assign_at_end,
    decode,
    encode,
    make_producer,
    new_correlation_id,
    setup_logging,
    short,
    trace,
)


class KafkaRequestTimeout(TimeoutError):
    """No response arrived for a correlation_id in time."""


class IncidentKafkaClient:
    """Send a request, wait for the response with the same correlation_id."""

    def __init__(self, component: str = "client", timeout_s: float = 30.0) -> None:
        self.component = component
        self.timeout_s = timeout_s
        self.log = setup_logging(component)
        self.producer = make_producer(f"{cfg.PREFIX}-{component}")
        self._consumer = Consumer({"bootstrap.servers": cfg.KAFKA_BOOTSTRAP,
                                   "group.id": f"{cfg.PREFIX}_{component}_{uuid.uuid4().hex[:8]}",
                                   "enable.auto.commit": False, "auto.offset.reset": "latest"})
        assign_at_end(self._consumer, cfg.RESPONSE_TOPIC)    # read only responses sent from now on
        self._pending: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._read_responses, daemon=True)
        self._thread.start()

    def _read_responses(self) -> None:
        """Background loop: match responses to waiting requests by correlation_id."""
        while not self._stop.is_set():
            msg = self._consumer.poll(0.5)
            if msg is None or msg.error():
                continue
            try:
                response = decode(msg.value())
            except ValueError:
                continue
            corr = response.get("correlation_id") if isinstance(response, dict) else None
            with self._lock:
                slot = self._pending.get(corr)
                if slot is not None:
                    slot["responses"].append(response)
                    slot["event"].set()

    def request(self, operation: str, data: dict, correlation_id: Optional[str] = None) -> dict:
        """Send one request and return the matching response (raises KafkaRequestTimeout)."""
        corr = correlation_id or new_correlation_id()      # created once, never changed afterwards
        message = {"correlation_id": corr, "reply_to": cfg.RESPONSE_TOPIC, "operation": operation, "data": data}
        slot = self.expect(corr)
        started = time.perf_counter()
        try:
            self.producer.produce(cfg.REQUEST_TOPIC, key=corr.encode(), value=encode(message))
            self.producer.flush(10)
            self.log.info("SEND -> %s corr=%s op=%s message=%s", cfg.REQUEST_TOPIC, corr, operation, short(message))
            trace(self.component, "client_sent", corr, operation=operation, topic=cfg.REQUEST_TOPIC)
            if not slot["event"].wait(self.timeout_s):
                raise KafkaRequestTimeout(f"no response for correlation_id {corr} within {self.timeout_s}s "
                                          "(is the worker running?)")
            response = slot["responses"][0]
        finally:
            with self._lock:
                self._pending.pop(corr, None)
        ms = (time.perf_counter() - started) * 1000
        self.log.info("RESPONSE <- %s corr=%s success=%s latency=%.0fms response=%s", cfg.RESPONSE_TOPIC, corr,
                      response.get("success"), ms, short(response))
        trace(self.component, "client_received", corr, operation=operation, topic=cfg.RESPONSE_TOPIC,
              success=response.get("success"), latency_ms=round(ms, 1),
              correlation_preserved=response.get("correlation_id") == corr)
        return response

    def expect(self, correlation_id: str) -> dict:
        """Register interest in a correlation_id before sending, so no response can be missed."""
        slot = {"event": threading.Event(), "responses": []}
        with self._lock:
            self._pending[correlation_id] = slot
        return slot

    def send_raw(self, message: Any, key: Optional[str] = None) -> None:
        """Send an arbitrary message to the request topic (used by the duplicate-replay test)."""
        self.producer.produce(cfg.REQUEST_TOPIC, key=key.encode() if key else None,
                              value=message if isinstance(message, bytes) else encode(message))
        self.producer.flush(10)

    def collect(self, correlation_id: str, count: int, timeout_s: float = 20.0) -> list[dict]:
        """Wait until `count` responses for a registered correlation_id arrived (or timeout)."""
        with self._lock:
            slot = self._pending.get(correlation_id)
        if slot is None:
            raise KeyError(f"call expect({correlation_id!r}) before sending")
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            with self._lock:
                if len(slot["responses"]) >= count:
                    break
            time.sleep(0.1)
        with self._lock:
            self._pending.pop(correlation_id, None)
            return list(slot["responses"])

    def close(self) -> None:
        """Stop the reader thread and close Kafka handles."""
        self._stop.set()
        self._thread.join(timeout=3)
        self._consumer.close()
        self.producer.flush(5)
