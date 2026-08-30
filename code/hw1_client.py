"""
hw1_client.py — DATA-260 HW1 Part 4: CLI demo using the model adapter

A small command-line chat demo that imports src/model_client.py's
ModelClient and uses it for every model call. After each response, prints
input/output/total tokens for that turn. On exit, prints cumulative
totals. Supports a /stats command that shows turn count, cumulative
token counts, and serialized conversation-history length, without
altering the conversation history.

Usage:
    python hw1_client.py
    (then type messages; type /stats to see usage; type /exit to quit)
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from model_client import ModelClient  # noqa: E402

SYSTEM_PROMPT = (
    "You are a helpful assistant for a municipal transit incident reporting "
    "system. Keep answers concise."
)


def print_stats(client: ModelClient, history: list):
    """
    Handles the /stats command: shows turn count, cumulative token
    counts, and the serialized length of the conversation history so
    far, WITHOUT modifying history or making any model call.
    """
    stats = client.stats()
    serialized_len = len(json.dumps(history))
    print("\n--- /stats ---")
    print(f"Turn count: {stats['turn_count']}")
    print(f"Cumulative input tokens:  {stats['cumulative_input_tokens']}")
    print(f"Cumulative output tokens: {stats['cumulative_output_tokens']}")
    print(f"Cumulative total tokens:  {stats['cumulative_total_tokens']}")
    print(f"Serialized conversation-history length: {serialized_len} characters")
    print("--------------\n")


def main():
    client = ModelClient(temperature=0.7)
    history = [{"role": "system", "content": SYSTEM_PROMPT}]

    print("HW1 CLI client (type /stats for usage stats, /exit to quit)\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            break

        if not user_input:
            continue

        if user_input == "/exit":
            break

        if user_input == "/stats":
            print_stats(client, history)
            continue

        history.append({"role": "user", "content": user_input})

        result = client.complete(history)
        history.append({"role": "assistant", "content": result.content})

        print(f"\nAssistant: {result.content}\n")
        print(
            f"[turn tokens — input: {result.input_tokens}, "
            f"output: {result.output_tokens}, total: {result.total_tokens}]\n"
        )

    # On exit: print cumulative totals
    final_stats = client.stats()
    print("\n=== Session summary ===")
    print(f"Total turns: {final_stats['turn_count']}")
    print(f"Cumulative input tokens:  {final_stats['cumulative_input_tokens']}")
    print(f"Cumulative output tokens: {final_stats['cumulative_output_tokens']}")
    print(f"Cumulative total tokens:  {final_stats['cumulative_total_tokens']}")


if __name__ == "__main__":
    main()