"""DATA-260 HW6 Part 4.5 - consolidation test on the 55-line MEMORY.md.

    python code/run_consolidation_test.py

Reads   reports/hw06/memory_test/MEMORY_original.md       (55 lines, committed as-is)
Writes  reports/hw06/memory_test/MEMORY_consolidated.md   (< 40 lines, committed)
        reports/hw06/raw/consolidation_report.json
Then checks the result against expected_resolutions.json (written by hand before the
run) to find any contradiction that was resolved incorrectly.
"""
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from file_memory import consolidate_file, consolidation_reasons, load_markdown, parse_memory  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
TEST_DIR = REPO / "reports" / "hw06" / "memory_test"
ORIGINAL = TEST_DIR / "MEMORY_original.md"
CONSOLIDATED = TEST_DIR / "MEMORY_consolidated.md"
EXPECTED = TEST_DIR / "expected_resolutions.json"
REPORT = REPO / "reports" / "hw06" / "raw" / "consolidation_report.json"


def main() -> None:
    """Run the consolidation and print a before/after audit."""
    original = load_markdown(ORIGINAL)
    print(f"Original: {ORIGINAL.relative_to(REPO)} - {len(original.splitlines())} lines")
    print("Consolidation required because:", "; ".join(consolidation_reasons(original)) or "no")

    shutil.copyfile(ORIGINAL, CONSOLIDATED)
    report = consolidate_file(CONSOLIDATED)
    result = load_markdown(CONSOLIDATED)
    current = {f.topic: f.text for f in parse_memory(result).facts}

    expected = {k: v for k, v in json.loads(EXPECTED.read_text()).items() if not k.startswith("_")}
    checks = []
    for topic, want in expected.items():
        got = current.get(topic, "")
        checks.append({"topic": topic, "expected": want, "kept": got,
                       "correct": want.lower() in got.lower()})
    superseded_text = result.split("## Superseded", 1)[-1] if "## Superseded" in result else ""
    lost = [s["text"] for c in report["contradictions"] for s in c["superseded"]
            if s["text"] not in superseded_text]
    report.update({
        "resolution_checks": checks,
        "incorrect_resolutions": [c for c in checks if not c["correct"]],
        "conflicting_values_lost": lost,
        "under_40_lines": report["lines_after"] < 40,
        "original_file": str(ORIGINAL.relative_to(REPO)),
        "consolidated_file": str(CONSOLIDATED.relative_to(REPO)),
    })
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2))

    print(f"Consolidated: {CONSOLIDATED.relative_to(REPO)} - {report['lines_after']} lines "
          f"(facts {report['facts_before']} -> {report['facts_after']})")
    print(f"Duplicates merged: {len(report['duplicates_merged'])} lines")
    print(f"Contradictions resolved: {len(report['contradictions'])}")
    for c in report["contradictions"]:
        old = " | ".join(s["text"] for s in c["superseded"])
        print(f"  [{c['flag']:6}] {c['topic']}: kept \"{c['kept']}\"  (superseded: {old})")
    print("Check against expected_resolutions.json:")
    for c in checks:
        print(f"  {'OK  ' if c['correct'] else 'WRONG'} {c['topic']}: expected '{c['expected']}', "
              f"kept \"{c['kept']}\"")
    print(f"Conflicting values silently lost: {len(lost)}")
    print(f"Under 40 lines: {report['under_40_lines']}")
    print(f"Report: {REPORT.relative_to(REPO)}")


if __name__ == "__main__":
    main()
