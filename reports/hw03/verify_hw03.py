"""
HW3 Self-Verification Script
SID4 = 1346 | DOMAIN_ID = 2 (Municipal Transit Incidents)

Checks that all required HW3 deliverables exist and are structurally valid.
Does NOT re-run the pipeline or re-check content correctness -- just presence,
format, and basic consistency (sizes, hashes, required fields).

Usage:
    python3 verify_hw03.py

Writes:
    verification.json
"""

import hashlib
import json
import os
import sys

try:
    import yaml
except ImportError:
    print("ERROR: pyyaml not installed. Run: pip install pyyaml")
    sys.exit(1)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CODE_AUTH_DIR = os.path.join(os.path.dirname(BASE_DIR), "..", "code", "auth_app")

checks = []


def check(name, passed, detail=""):
    status = "PASS" if passed else "FAIL"
    checks.append({"check": name, "status": status, "detail": detail})
    print(f"[{status}] {name}" + (f" -- {detail}" if detail else ""))
    return passed


def main():
    print("=== HW3 Verification ===\n")

    # --- Part 1: Auth app files exist ---
    print("--- Part 1: Auth App ---")
    auth_files = ["main.py", "auth.py", "templates/base.html",
                  "templates/home.html", "templates/login.html", "templates/dashboard.html"]
    for f in auth_files:
        path = os.path.normpath(os.path.join(CODE_AUTH_DIR, f))
        check(f"auth_app/{f} exists", os.path.isfile(path), path)

    # --- Part 2: Corpus ---
    print("\n--- Part 2: Corpus ---")
    corpus_dir = os.path.join(BASE_DIR, "corpus")
    check("corpus/ directory exists", os.path.isdir(corpus_dir))

    manifest_path = os.path.join(corpus_dir, "CORPUS_MANIFEST.json")
    manifest_ok = check("CORPUS_MANIFEST.json exists", os.path.isfile(manifest_path))

    total_bytes = 0
    manifest = None
    if manifest_ok:
        with open(manifest_path) as f:
            manifest = json.load(f)
        check("CORPUS_MANIFEST.json has 'files' list", "files" in manifest and len(manifest["files"]) > 0,
              f"{len(manifest.get('files', []))} entries")

        # Verify every listed file actually exists and hash matches
        hash_mismatches = []
        missing_files = []
        for entry in manifest.get("files", []):
            fpath = os.path.join(corpus_dir, entry["filename"])
            if not os.path.isfile(fpath):
                missing_files.append(entry["filename"])
                continue
            with open(fpath, "rb") as f:
                data = f.read()
            total_bytes += len(data)
            actual_hash = hashlib.sha256(data).hexdigest()
            if actual_hash != entry.get("sha256"):
                hash_mismatches.append(entry["filename"])

        check("All manifest files present on disk", len(missing_files) == 0,
              f"missing: {missing_files}" if missing_files else "")
        check("All manifest SHA-256 hashes match actual files", len(hash_mismatches) == 0,
              f"mismatched: {hash_mismatches}" if hash_mismatches else "")
        check("Corpus total size >= 200,000 bytes", total_bytes >= 200000,
              f"{total_bytes} bytes")
        check("Corpus total size >= 204,800 bytes (200 KiB)", total_bytes >= 204800,
              f"{total_bytes} bytes")

    check("SOURCES.md exists", os.path.isfile(os.path.join(corpus_dir, "SOURCES.md")))

    # Flag known problem file if it somehow reappears
    leak_file = os.path.join(corpus_dir, "questions_source_mapping_notes.txt")
    check("Known leaking file (questions_source_mapping_notes.txt) is NOT present",
          not os.path.isfile(leak_file))

    # --- questions.yaml ---
    print("\n--- questions.yaml ---")
    q_path = os.path.join(BASE_DIR, "questions.yaml")
    q_ok = check("questions.yaml exists", os.path.isfile(q_path))
    q_data = None
    if q_ok:
        with open(q_path) as f:
            q_data = yaml.safe_load(f)
        questions = q_data.get("questions", [])
        check("questions.yaml has exactly 5 questions", len(questions) == 5, f"found {len(questions)}")

        single_source = [q for q in questions if q.get("question_type") == "single_source"]
        multi_source = [q for q in questions if q.get("question_type") == "multi_source"]
        check("At least 2 single_source questions", len(single_source) >= 2,
              f"found {len(single_source)}")
        check("At least 1 multi_source question", len(multi_source) >= 1,
              f"found {len(multi_source)}")

        required_fields = ["id", "question", "question_type", "source_files", "expected_answer"]
        missing_fields = []
        for q in questions:
            for field in required_fields:
                if field not in q:
                    missing_fields.append(f"{q.get('id', '?')}.{field}")
        check("All questions have required fields", len(missing_fields) == 0,
              f"missing: {missing_fields}" if missing_fields else "")

    # --- Pipeline outputs ---
    print("\n--- Pipeline Outputs ---")
    raw_dir = os.path.join(BASE_DIR, "raw")
    check("raw/ directory exists", os.path.isdir(raw_dir))
    for pipeline in ["token", "semantic", "sentence_window"]:
        p = os.path.join(raw_dir, f"{pipeline}_results.json")
        ok = check(f"raw/{pipeline}_results.json exists", os.path.isfile(p))
        if ok:
            with open(p) as f:
                data = json.load(f)
            n_results = len(data.get("results", []))
            check(f"{pipeline}_results.json has 5 question results", n_results == 5,
                  f"found {n_results}")
            n_hits = sum(1 for r in data["results"] if r.get("hit_expected_source_file"))
            print(f"       -> {pipeline}: {n_hits}/5 hit expected source, "
                  f"{data.get('num_chunks', '?')} chunks, {data.get('elapsed_seconds', '?')}s")

    check("RUN_LOG.txt exists", os.path.isfile(os.path.join(BASE_DIR, "RUN_LOG.txt")))

    # --- Reporting docs ---
    print("\n--- Reporting Documents ---")
    check("METRICS.md exists", os.path.isfile(os.path.join(BASE_DIR, "METRICS.md")))
    check("AI_USE.md exists", os.path.isfile(os.path.join(BASE_DIR, "AI_USE.md")))

    metrics_path = os.path.join(BASE_DIR, "METRICS.md")
    if os.path.isfile(metrics_path):
        with open(metrics_path) as f:
            metrics_text = f.read()
        check("METRICS.md contains an Analysis section", "## Analysis" in metrics_text)
        check("METRICS.md contains a Conclusion section", "## Conclusion" in metrics_text)

    # --- Summary ---
    print("\n=== Summary ===")
    n_pass = sum(1 for c in checks if c["status"] == "PASS")
    n_fail = sum(1 for c in checks if c["status"] == "FAIL")
    print(f"{n_pass} passed, {n_fail} failed, {len(checks)} total")

    result = {
        "sid4": 1346,
        "domain_id": 2,
        "corpus_total_bytes": total_bytes,
        "checks_passed": n_pass,
        "checks_failed": n_fail,
        "checks_total": len(checks),
        "all_passed": n_fail == 0,
        "checks": checks,
    }

    out_path = os.path.join(BASE_DIR, "verification.json")
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)
    print(f"\nWrote {out_path}")

    if n_fail > 0:
        print("\n*** SOME CHECKS FAILED -- review before submitting ***")
        sys.exit(1)
    else:
        print("\nAll checks passed.")


if __name__ == "__main__":
    main()