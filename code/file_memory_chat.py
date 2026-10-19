"""DATA-260 HW6 Part 4 - chat CLI with file-based memory (AGENT.md + MEMORY.md).

    python code/file_memory_chat.py                         # uses ./AGENT.md and ./MEMORY.md
    python code/file_memory_chat.py --memory-file /tmp/M.md  # work on a copy

Commands:
  /memory   show the current file-based memory (AGENT.md + MEMORY.md + status)
  /compact  consolidate MEMORY.md and compact the conversation; reports counts before/after
  /dream    extract durable facts from the recent conversation and add them to MEMORY.md
  /help     list the commands
  /exit     quit
Every model call goes through src/model_client.py (AGENT.md rule T2).
"""
import argparse
import getpass
import platform
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import file_memory as fm  # noqa: E402
from model_client import ModelClient  # noqa: E402

BASE_PROMPT = ("You are TransitDesk, the assistant for the s1346 Municipal Transit Incidents "
               "project. Follow the project instructions and use the durable memory below.")
KEEP_RECENT = 4          # messages kept verbatim by /compact
DREAM_WINDOW = 20        # messages /dream looks at

HELP = """Commands:
  /memory   show AGENT.md, MEMORY.md and whether consolidation is required
  /compact  consolidate MEMORY.md (merge duplicates, resolve contradictions) and compact
            the conversation history; prints message/line counts before and after
  /dream    find durable facts in the recent conversation and append them to MEMORY.md
  /help     show this help
  /exit     quit"""

DREAM_PROMPT = (
    "From the conversation below, list the durable facts worth remembering in future "
    "sessions (about the user, their project, decisions and preferences). Skip anything "
    "temporary or general knowledge. One fact per line, exactly in the form:\n"
    "(topic) Fact sentence.\n"
    "Topics are short, lowercase and dotted (user.name, project.port, preference.format). "
    "Reuse one of these existing topics when the fact is about the same thing: {topics}.\n"
    "If there is nothing worth remembering, output NONE.\n\nCONVERSATION:\n{transcript}"
)

SUMMARY_PROMPT = ("Summarise this earlier part of the conversation in at most 5 short bullet "
                  "points, keeping names, numbers and decisions:\n\n{transcript}")


def transcript(messages: list) -> str:
    """Render chat messages as 'role: content' lines."""
    return "\n".join(f"{m['role']}: {m['content']}" for m in messages)


class FileMemoryChat:
    """Chat session whose system prompt is rebuilt from AGENT.md + MEMORY.md every turn."""

    def __init__(self, agent_path: Path, memory_path: Path, client: ModelClient) -> None:
        self.agent_path = agent_path
        self.memory_path = memory_path
        self.client = client
        self.history: list = []          # user/assistant messages (system prompt built per turn)

    def system_prompt(self) -> str:
        """Current system prompt built from both Markdown files."""
        agent, memory = fm.load_memory_files(self.agent_path, self.memory_path)
        return fm.build_system_prompt(BASE_PROMPT, agent, memory)

    def ask(self, text: str) -> str:
        """Send one user message with the file-based memory in the system prompt."""
        self.history.append({"role": "user", "content": text})
        messages = [{"role": "system", "content": self.system_prompt()}, *self.history]
        result = self.client.complete(messages)
        self.history.append({"role": "assistant", "content": result.content.strip()})
        return f"{result.content.strip()}\n  [tokens in={result.input_tokens} out={result.output_tokens}]"

    def cmd_memory(self) -> str:
        """/memory: show both files and the consolidation status."""
        agent, memory = fm.load_memory_files(self.agent_path, self.memory_path)
        reasons = fm.consolidation_reasons(memory)
        stamp = fm.read_last_consolidated(memory)
        return (f"===== AGENT.md ({self.agent_path}) =====\n{agent.strip()}\n\n"
                f"===== MEMORY.md ({self.memory_path}) =====\n{memory.strip()}\n\n"
                f"----- status -----\n"
                f"content lines (non-empty, non-comment): {fm.count_content_lines(memory)} "
                f"(limit {fm.MAX_MEMORY_LINES})\n"
                f"last consolidated: {stamp.isoformat() if stamp else 'never'}\n"
                f"consolidation required: {'YES - ' + '; '.join(reasons) if reasons else 'no'}")

    def cmd_compact(self) -> str:
        """/compact: consolidate MEMORY.md and compact the conversation history."""
        msgs_before = len(self.history)
        note = "history short enough - nothing to compact"
        if msgs_before > KEEP_RECENT:
            older, recent = self.history[:-KEEP_RECENT], self.history[-KEEP_RECENT:]
            try:
                summary = self.client.complete([{"role": "user", "content":
                                                 SUMMARY_PROMPT.format(transcript=transcript(older))}])
                self.history = [{"role": "assistant", "content":
                                 "Summary of the earlier conversation:\n" + summary.content.strip()},
                                *recent]
                note = f"{len(older)} older messages summarised into 1"
            except Exception as exc:                  # noqa: BLE001 - keep history if the model is down
                note = f"history kept (model unavailable: {exc.__class__.__name__})"
        report = fm.consolidate_file(self.memory_path)
        lines = [
            "/compact report",
            f"  conversation messages : {msgs_before} -> {len(self.history)}  ({note})",
            f"  MEMORY.md lines       : {report['lines_before']} -> {report['lines_after']}",
            f"  content lines         : {report['content_lines_before']} -> {report['content_lines_after']}",
            f"  facts                 : {report['facts_before']} -> {report['facts_after']}",
            f"  duplicate lines merged: {len(report['duplicates_merged'])}",
            f"  contradictions        : {len(report['contradictions'])} resolved, "
            f"{report['superseded_lines']} value(s) in ## Superseded",
        ]
        for c in report["contradictions"]:
            old = " | ".join(s["text"] for s in c["superseded"])
            lines.append(f"    [{c['flag']}] {c['topic']}: kept \"{c['kept']}\" (was: {old})")
        return "\n".join(lines)

    def cmd_dream(self) -> str:
        """/dream: append durable facts from the recent conversation to MEMORY.md."""
        recent = self.history[-DREAM_WINDOW:]
        if not recent:
            return "/dream: no conversation yet - nothing to learn"
        _, memory = fm.load_memory_files(self.agent_path, self.memory_path)
        topics = sorted({f.topic for f in fm.parse_memory(memory).facts}) or ["(none yet)"]
        result = self.client.complete([{"role": "user", "content": DREAM_PROMPT.format(
            topics=", ".join(topics), transcript=transcript(recent))}], options={"temperature": 0})
        candidates = fm.parse_dream_output(result.content)
        added = fm.append_facts(self.memory_path, candidates)
        lines = [f"/dream: looked at {len(recent)} messages, model proposed {len(candidates)} fact(s), "
                 f"added {len(added)} (duplicates skipped)"]
        lines += [f"  + {a}" for a in added]
        _, memory = fm.load_memory_files(self.agent_path, self.memory_path)
        if fm.needs_consolidation(memory):
            lines.append("  note: consolidation now required - run /compact")
        return "\n".join(lines)

    def handle(self, line: str) -> str:
        """Dispatch a command or a normal chat message."""
        command = line.strip().split()[0].lower() if line.strip().startswith("/") else None
        if command == "/memory":
            return self.cmd_memory()
        if command == "/compact":
            return self.cmd_compact()
        if command == "/dream":
            return self.cmd_dream()
        if command == "/help":
            return HELP
        if command:
            return f"Unknown command {command}. Type /help."
        return self.ask(line)


def main() -> None:
    """Interactive loop (also works with piped input)."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent-file", type=Path, default=fm.AGENT_PATH)
    ap.add_argument("--memory-file", type=Path, default=fm.MEMORY_PATH)
    args = ap.parse_args()

    chat = FileMemoryChat(args.agent_file, args.memory_file,
                          ModelClient(temperature=0.3, seed=1346, num_predict=300))
    print(f"DATA-260 HW6 file-memory chat | s1346 | user: {getpass.getuser()}@{platform.node()}")
    print(f"AGENT.md: {args.agent_file}\nMEMORY.md: {args.memory_file}")
    _, memory = fm.load_memory_files(args.agent_file, args.memory_file)
    reasons = fm.consolidation_reasons(memory)
    print(f"Consolidation required: {'YES - ' + '; '.join(reasons) if reasons else 'no'}")
    print("Type /help for commands.\n")
    while True:
        try:
            line = input("you> ")
        except EOFError:
            break
        if not sys.stdin.isatty():
            print(line)                      # echo piped input so logs show the command
        if not line.strip():
            continue
        if line.strip().lower() in ("/exit", "/quit"):
            break
        try:
            print(chat.handle(line) + "\n")
        except Exception as exc:                 # noqa: BLE001 - keep the CLI alive
            print(f"[error] {exc.__class__.__name__}: {exc}\n")


if __name__ == "__main__":
    main()
