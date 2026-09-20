# AI_USE.md — HW3

## Tool used
Claude (Anthropic), used conversationally throughout both Part 1 and Part 2, with the person
running all commands themselves in their own terminal/VS Code environment.

## Part 1 — FastAPI Auth App
Claude helped design and write the FastAPI app (`main.py`, `auth.py`, Bootstrap templates),
including session cookie configuration (`httponly`, `samesite=lax`, `secure`) and the server-side
idle-timeout logic. Claude also helped debug a Starlette API version mismatch
(`TemplateResponse` argument order) encountered during testing. All verification (browser
testing, DevTools inspection of cookies, timing the idle timeout) was performed by the person
directly, not simulated or asserted by Claude.

## Part 2 — Chunking Comparison

**Corpus sourcing.** Claude searched for and fetched real, publicly available NTSB accident
reports and FTA/UMTA policy documents via live web requests, condensing each into a
corpus file with the original source URL and access date recorded in its header.

**Integrity issue and correction (disclosed in full).** During corpus assembly, four files were
discovered to have been created without a corresponding verified fetch in the working session —
in other words, unverified content that could not be confirmed against a real source. All four
were identified and deleted immediately upon discovery; two of the same topics were then
independently re-researched and re-fetched with confirmed live retrieval. This is documented in
detail in `corpus/corpus_index_and_coverage_notes.txt` and `corpus/SOURCES.md`.

A second, separate issue was caught later, during the Part 2 metrics analysis: one corpus file
(`questions_source_mapping_notes.txt`), created while drafting `questions.yaml`, contained
language that closely paired each graded question's expected fact with its source filename —
functioning as an inadvertent answer key sitting inside the retrieval corpus. This was discovered
by inspecting the sentence-window pipeline's retrieval results, where that file was scoring as the
closest semantic match to several questions. The file was removed from the corpus, the
manifest and `SOURCES.md` were regenerated, and the full chunking-comparison pipeline was
re-run from scratch on the corrected corpus before any metrics or analysis were finalized. The
`METRICS.md` and analysis in this report reflect only the corrected, post-fix run.

**Pipeline code.** Claude wrote `run_chunking_comparison.py` (the three LlamaIndex chunking
pipelines: token-based, semantic, sentence-window, plus FAISS-backed retrieval) and
`generate_metrics.py` (which parses the raw JSON results into `METRICS.md`). Claude tested
the chunking and retrieval logic against the real corpus and question set using a mock embedding
model, since the development sandbox could not reach Hugging Face's servers to download the
real embedding model. The live embedding model (`BAAI/bge-small-en-v1.5`) was downloaded
and run for real exclusively on the person's own machine; Claude never executed the actual
retrieval run against real embeddings itself.

**Analysis and conclusion.** Claude drafted the analysis and conclusion in `METRICS.md` after
being given the actual `METRICS.md` output from the person's real run (both the contaminated
first run and the corrected second run), interpreting the real retrieval scores rather than
predicting or assuming what they would be.

## What the person did directly
Ran every installation command, executed both pipeline scripts on their own machine, verified
file placement and git status at each step, committed and pushed all work to GitHub, and
caught/relayed the actual terminal output that led to identifying the second (question-leakage)
integrity issue.