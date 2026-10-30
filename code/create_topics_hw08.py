"""Create / describe the seven s1346 HW8 topics with the Kafka AdminClient.

The report uses the Kafka CLI (make hw08-topics runs kafka-topics.sh inside the broker container);
this script is the same thing from Python, used by verify_hw08.py and when no CLI is at hand.

    python code/create_topics_hw08.py            # create missing topics, then describe all
    python code/create_topics_hw08.py --describe
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from confluent_kafka.admin import NewTopic  # noqa: E402

import hw08_config as cfg  # noqa: E402
from kafka_common import admin, topic_partitions, wait_for_broker  # noqa: E402


def main() -> None:
    """Create missing topics and print partition counts."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--describe", action="store_true")
    args = ap.parse_args()
    wait_for_broker()
    if not args.describe:
        existing = topic_partitions()
        new = [NewTopic(t, num_partitions=p, replication_factor=1) for t, p in cfg.TOPICS.items() if t not in existing]
        client = admin()                       # keep a reference until the futures resolve
        for topic, fut in (client.create_topics(new).items() if new else []):
            fut.result()
            print(f"created {topic}")
    have = topic_partitions()
    for topic, want in cfg.TOPICS.items():
        got = have.get(topic)
        print(f"{topic:28s} partitions={got} (expected {want}) {'OK' if got == want else 'MISMATCH'}")


if __name__ == "__main__":
    main()
