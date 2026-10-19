"""DATA-260 HW6 Part 4 - file-based memory (AGENT.md + MEMORY.md).

AGENT.md  - durable project and agent instructions (hand-written).
MEMORY.md - durable facts learned from conversations, one per line:

    - [YYYY-MM-DD] (topic) Fact sentence.

A topic holds ONE current value. Consolidation:
  * duplicates   - same topic and (near-)identical text -> merged into one line that
                   records how often it was seen (`<!-- seen:N first:DATE -->`)
  * contradictions - same topic, different text -> the newest-dated statement stays in
                   ## Facts; every older value is MOVED to ## Superseded with what replaced
                   it and the rule used (never silently deleted). If the winning statement is
                   tentative ("thinking about", "maybe", ...) the resolution is flagged REVIEW.
  * anything that does not parse is kept verbatim under ## Unstructured notes.
Consolidation is deterministic (no LLM): a 3B local model cannot be trusted to
rewrite a 55-line file without dropping facts, and a rule-based merge is auditable.
"""
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger("s1346.file_memory")

REPO_ROOT = Path(__file__).resolve().parents[1]
AGENT_PATH = REPO_ROOT / "AGENT.md"
MEMORY_PATH = REPO_ROOT / "MEMORY.md"

MAX_MEMORY_LINES = 40
MAX_AGE = timedelta(hours=24)

FACT_RE = re.compile(r"^- \[(\d{4}-\d{2}-\d{2})\] \(([\w.\-]+)\) (.+?)\s*(<!--\s*(.*?)\s*-->)?\s*$")
SUPERSEDED_RE = re.compile(r"^- \[(\d{4}-\d{2}-\d{2})\] \(([\w.\-]+)\) ")
STAMP_RE = re.compile(r"<!--\s*last_consolidated:\s*(\S+)\s*-->")
HEDGE_RE = re.compile(r"\b(maybe|might|possibly|perhaps|considering|thinking about|"
                      r"planning to|plans to|if\b|unconfirmed|not sure|rumou?r)", re.I)
DUPLICATE_JACCARD = 0.75

HEADER = "# MEMORY.md - durable facts learned from conversations (s1346)"
FORMAT_NOTE = ("<!-- format: - [YYYY-MM-DD] (topic) Fact. One topic = one current value; "
               "a newer fact on the same topic supersedes the older one. -->")


# ---- loading + prompt -----------------------------------------------------------------
def load_markdown(path: Path) -> str:
    """Return a Markdown file's text, or an empty string if it does not exist."""
    return path.read_text(encoding="utf-8") if path.exists() else ""


def load_memory_files(agent_path: Path = AGENT_PATH, memory_path: Path = MEMORY_PATH) -> tuple:
    """Load AGENT.md and MEMORY.md. Returns (agent_text, memory_text)."""
    return load_markdown(agent_path), load_markdown(memory_path)


def _strip_comments(text: str) -> str:
    """Remove HTML comments (single- or multi-line)."""
    return re.sub(r"<!--.*?-->", "", text, flags=re.S)


def memory_for_prompt(memory_text: str) -> str:
    """MEMORY.md without comments and without the ## Superseded audit section."""
    text = re.split(r"^## Superseded.*$", memory_text, maxsplit=1, flags=re.M)[0]
    return "\n".join(l for l in _strip_comments(text).splitlines() if l.strip()).strip()


def build_system_prompt(base_prompt: str, agent_text: str, memory_text: str) -> str:
    """System prompt = base prompt + AGENT.md instructions + current MEMORY.md facts."""
    parts = [base_prompt.strip()]
    if agent_text.strip():
        parts.append("# Project and agent instructions (AGENT.md)\n"
                     + _strip_comments(agent_text).strip())
    facts = memory_for_prompt(memory_text)
    if facts:
        parts.append("# Durable memory (MEMORY.md) - facts from earlier conversations; "
                     "the newest value of a topic is the current one\n" + facts)
    return "\n\n".join(parts)


# ---- consolidation checks ---------------------------------------------------------------
def count_content_lines(memory_text: str) -> int:
    """Number of non-empty, non-comment lines."""
    return sum(1 for l in _strip_comments(memory_text).splitlines() if l.strip())


def read_last_consolidated(memory_text: str) -> Optional[datetime]:
    """The `<!-- last_consolidated: ISO -->` timestamp, or None if missing/invalid."""
    match = STAMP_RE.search(memory_text)
    if not match:
        return None
    try:
        stamp = datetime.fromisoformat(match.group(1))
    except ValueError:
        return None
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)


def consolidation_reasons(memory_text: str, now: Optional[datetime] = None) -> list:
    """Why consolidation is required (empty list = not required)."""
    now = now or datetime.now(timezone.utc)
    reasons = []
    lines = count_content_lines(memory_text)
    if lines > MAX_MEMORY_LINES:
        reasons.append(f"{lines} non-empty, non-comment lines > {MAX_MEMORY_LINES}")
    stamp = read_last_consolidated(memory_text)
    if stamp is None:
        reasons.append("no last_consolidated timestamp recorded")
    elif now - stamp > MAX_AGE:
        hours = (now - stamp).total_seconds() / 3600
        reasons.append(f"last consolidated {hours:.1f} h ago (> 24 h)")
    return reasons


def needs_consolidation(memory_text: str, now: Optional[datetime] = None) -> bool:
    """True if MEMORY.md has > 40 content lines or was consolidated more than 24 h ago."""
    return bool(consolidation_reasons(memory_text, now))


# ---- parsing --------------------------------------------------------------------------------
@dataclass
class Fact:
    """One parsed MEMORY.md fact line."""
    date: str
    topic: str
    text: str
    seen: int = 1
    first: str = ""
    line_no: int = 0

    def render(self) -> str:
        """Back to a MEMORY.md line (with the seen/first note when merged)."""
        note = f"  <!-- seen:{self.seen} first:{self.first} -->" if self.seen > 1 else ""
        return f"- [{self.date}] ({self.topic}) {self.text}{note}"


@dataclass
class ParsedMemory:
    """MEMORY.md split into its parts."""
    facts: list = field(default_factory=list)
    superseded: list = field(default_factory=list)     # existing audit lines, kept verbatim
    unstructured: list = field(default_factory=list)   # lines that are not facts, kept verbatim


def parse_memory(memory_text: str) -> ParsedMemory:
    """Split MEMORY.md into facts, superseded audit lines and unstructured lines."""
    parsed, section = ParsedMemory(), "facts"
    for no, raw in enumerate(memory_text.splitlines(), start=1):
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("<!--") or stripped.startswith("# "):
            continue
        if stripped.startswith("## "):
            title = stripped[3:].lower()
            section = ("superseded" if title.startswith("superseded")
                       else "unstructured" if title.startswith("unstructured") else "facts")
            continue
        if section == "superseded":
            parsed.superseded.append(stripped)
            continue
        match = FACT_RE.match(stripped)
        if match and section == "facts":
            date, topic, text, _, note = match.groups()
            seen = int(re.search(r"seen:(\d+)", note or "seen:1").group(1))
            first = (re.search(r"first:(\S+)", note or "") or [None, date])[1]
            parsed.facts.append(Fact(date, topic, text.strip(), seen, first, no))
        else:
            parsed.unstructured.append(stripped)
    return parsed


def _words(text: str) -> set:
    """Lower-case word set used for duplicate detection."""
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def is_duplicate(a: str, b: str, threshold: float = DUPLICATE_JACCARD) -> bool:
    """Two fact texts are duplicates if their word sets overlap (Jaccard) >= threshold."""
    wa, wb = _words(a), _words(b)
    if not wa or not wb:
        return a.strip().lower() == b.strip().lower()
    return len(wa & wb) / len(wa | wb) >= threshold


# ---- consolidation ---------------------------------------------------------------------------
def consolidate_text(memory_text: str, now: Optional[datetime] = None) -> tuple:
    """Consolidate MEMORY.md text. Returns (new_text, report_dict)."""
    now = now or datetime.now(timezone.utc)
    parsed = parse_memory(memory_text)
    report = {"lines_before": len(memory_text.splitlines()),
              "content_lines_before": count_content_lines(memory_text),
              "facts_before": len(parsed.facts), "duplicates_merged": [],
              "contradictions": [], "unstructured_kept": list(parsed.unstructured)}

    # 1. merge duplicates inside each topic (keep newest date, count + first-seen date)
    topics: dict = {}
    for fact in parsed.facts:
        group = topics.setdefault(fact.topic, [])
        twin = next((g for g in group if is_duplicate(g.text, fact.text)), None)
        if twin is None:
            group.append(Fact(fact.date, fact.topic, fact.text, fact.seen, fact.first or fact.date,
                              fact.line_no))
            continue
        report["duplicates_merged"].append({"topic": fact.topic, "kept": twin.text,
                                            "merged_line": fact.line_no, "merged_text": fact.text})
        twin.seen += fact.seen
        twin.first = min(twin.first, fact.first or fact.date)
        if (fact.date, fact.line_no) > (twin.date, twin.line_no):   # newer wording wins
            twin.date, twin.text, twin.line_no = fact.date, fact.text, fact.line_no

    # 2. resolve contradictions explicitly: newest date wins, older values are superseded
    current, superseded = [], list(parsed.superseded)
    for topic, group in topics.items():
        group.sort(key=lambda f: (f.date, f.line_no))
        winner = group[-1]
        current.append(winner)
        if len(group) == 1:
            continue
        flag = "REVIEW" if HEDGE_RE.search(winner.text) else "ok"
        losers = group[:-1]
        for old in losers:
            note = " ⚠ REVIEW: newer statement is tentative" if flag == "REVIEW" else ""
            superseded.append(f"- [{old.date}] ({topic}) {old.text} -> replaced on {winner.date} by: "
                              f"\"{winner.text}\" (rule: newest dated statement wins){note}")
        report["contradictions"].append({
            "topic": topic, "kept": winner.text, "kept_date": winner.date,
            "superseded": [{"date": o.date, "text": o.text} for o in losers], "flag": flag})

    current.sort(key=lambda f: (f.topic, f.date))
    stamp = now.astimezone().isoformat(timespec="seconds")
    lines = [HEADER, f"<!-- last_consolidated: {stamp} -->", FORMAT_NOTE, "", "## Facts"]
    lines += [f.render() for f in current]
    if superseded:
        lines += ["", "## Superseded (kept for audit - not current facts)"] + superseded
    if parsed.unstructured:
        lines += ["", "## Unstructured notes"] + parsed.unstructured
    new_text = "\n".join(lines) + "\n"

    report.update({"lines_after": len(new_text.splitlines()),
                   "content_lines_after": count_content_lines(new_text),
                   "facts_after": len(current), "superseded_lines": len(superseded),
                   "consolidated_at": stamp})
    return new_text, report


def consolidate_file(path: Path = MEMORY_PATH, now: Optional[datetime] = None) -> dict:
    """Consolidate a MEMORY.md file in place and return the report."""
    new_text, report = consolidate_text(load_markdown(path), now)
    path.write_text(new_text, encoding="utf-8")
    log.info("consolidated %s: %s -> %s lines", path, report["lines_before"], report["lines_after"])
    return report


# ---- adding facts (/dream) -------------------------------------------------------------------
DREAM_LINE_RE = re.compile(r"^\s*[-*]?\s*\(([\w.\-]+)\)\s*(.+?)\s*$")


def parse_dream_output(reply: str) -> list:
    """Parse model lines of the form `(topic) fact` into (topic, text) pairs."""
    out = []
    for line in reply.splitlines():
        match = DREAM_LINE_RE.match(line)
        if match and 3 <= len(match.group(2)) <= 200:
            out.append((match.group(1).lower(), match.group(2).rstrip()))
    return out


def append_facts(path: Path, facts: list, today: Optional[str] = None) -> list:
    """Append (topic, text) facts under ## Facts unless the fact is already its topic's current value.

    Contradicting facts ARE appended - they are resolved (not lost) at the next consolidation.
    Returns the lines actually added.
    """
    today = today or datetime.now().strftime("%Y-%m-%d")
    text = load_markdown(path) or f"{HEADER}\n{FORMAT_NOTE}\n\n## Facts\n"
    existing = parse_memory(text).facts
    added = []
    for topic, fact in facts:
        same_topic = sorted((f for f in existing if f.topic == topic), key=lambda f: f.date)
        if same_topic and is_duplicate(same_topic[-1].text, fact):
            continue        # already the current value; re-stating an OLDER value re-asserts it
        new = Fact(today, topic, fact)
        existing.append(new)
        added.append(new.render())
    if not added:
        return []
    lines = text.splitlines()
    try:
        start = next(i for i, l in enumerate(lines) if l.strip().lower() == "## facts")
        end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
        while end > start + 1 and not lines[end - 1].strip():
            end -= 1
        lines[end:end] = added
    except StopIteration:
        lines += ["", "## Facts"] + added
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return added
