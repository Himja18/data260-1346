"""HW8 Part 1 - Incident worker: consumes s1346_incident_requests, replies on the topic named by reply_to.

    python code/kafka_service/worker.py                     # normal (idempotent) worker
    python code/kafka_service/worker.py --no-idempotency    # "before fix" mode for the duplicate-replay demo

The offset of a request is committed only after its response has been delivered to Kafka.
Unparseable messages (not JSON) cannot be answered, so they go to s1346_dead_letter.
"""
import argparse
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import hw08_config as cfg  # noqa: E402
from incident_service import IncidentService  # noqa: E402
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

COMPONENT = "worker"


def main() -> None:
    """Run the consume -> validate/process -> reply -> commit loop."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--no-idempotency", action="store_true", help="process replays again (before-fix demo)")
    ap.add_argument("--group", default=cfg.WORKER_GROUP)
    args = ap.parse_args()

    log = setup_logging(COMPONENT)
    wait_for_broker(log)
    require_topics([cfg.REQUEST_TOPIC, cfg.RESPONSE_TOPIC, cfg.DEAD_LETTER_TOPIC], log, wait_s=600)

    service = IncidentService(idempotent=not args.no_idempotency)
    producer = make_producer(f"{cfg.PREFIX}-incident-worker")
    consumer = make_consumer(args.group, f"{cfg.PREFIX}-incident-worker")
    ready = {"logged": False}

    def on_assign(c, partitions) -> None:  # noqa: ANN001
        log.info("partitions assigned: %s", [f"{p.topic}[{p.partition}]" for p in partitions])
        if not ready["logged"]:
            log.info("Consumer is ready and listening... topic=%s group=%s idempotency=%s",
                     cfg.REQUEST_TOPIC, args.group, "on" if service.idempotent else "OFF")
            ready["logged"] = True

    consumer.subscribe([cfg.REQUEST_TOPIC], on_assign=on_assign)
    running = {"on": True}
    signal.signal(signal.SIGTERM, lambda *_: running.update(on=False))

    try:
        while running["on"]:
            msg = consumer.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                log.warning("consumer error: %s", msg.error())
                continue
            where = f"{msg.topic()}[{msg.partition()}]@{msg.offset()}"
            try:
                request = decode(msg.value())
            except ValueError as exc:
                log.error("POISON %s is not valid JSON (%s) -> %s", where, exc, cfg.DEAD_LETTER_TOPIC)
                producer.produce(cfg.DEAD_LETTER_TOPIC, value=encode({
                    "source": COMPONENT, "topic": msg.topic(), "partition": msg.partition(),
                    "offset": msg.offset(), "error": f"invalid JSON: {exc}", "attempts": 1,
                    "raw_value": (msg.value() or b"").decode("utf-8", "replace"), "failed_at": now_iso()}))
                producer.flush(10)
                consumer.commit(message=msg, asynchronous=False)
                continue

            corr = request.get("correlation_id") if isinstance(request, dict) else None
            op = request.get("operation") if isinstance(request, dict) else None
            log.info("RECEIVED <- %s corr=%s op=%s message=%s", where, corr, op, short(request))
            trace(COMPONENT, "worker_received", corr, operation=op, topic=msg.topic(),
                  partition=msg.partition(), offset=msg.offset())

            response, duplicate = service.handle(request)
            if duplicate:
                log.info("DUPLICATE corr=%s already processed -> re-sending cached response, no new side effect "
                         "(store size %d)", corr, len(service.incidents))
            else:
                log.info("PROCESSED %s corr=%s success=%s store_size=%d", op, corr, response["success"],
                         len(service.incidents))
            trace(COMPONENT, "worker_processed", corr, operation=op, success=response["success"],
                  duplicate=duplicate, store_size=len(service.incidents),
                  incident_id=response.get("incident_id") or (response.get("incident") or {}).get("incident_id"))

            reply_topic = service.safe_reply_topic(request)
            producer.produce(reply_topic, key=(corr or "").encode() or None, value=encode(response))
            producer.flush(10)
            log.info("REPLY -> %s corr=%s response=%s", reply_topic, corr, short(response))
            trace(COMPONENT, "worker_replied", corr, topic=reply_topic, success=response["success"])
            consumer.commit(message=msg, asynchronous=False)        # commit only after the reply is delivered
    except KeyboardInterrupt:
        pass
    finally:
        log.info("worker stopping (incidents in memory: %d)", len(service.incidents))
        consumer.close()


if __name__ == "__main__":
    main()
