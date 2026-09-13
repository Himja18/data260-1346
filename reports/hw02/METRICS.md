# DATA-260 HW2 — Metrics

## Section 0 — Configuration

| Field | Value |
|---|---|
| SID4 | 1346 |
| PORT_BASE | 8446 |
| PREFIX | s1346 |
| SEED | 1346 |
| VERIFY_SEED | 261346 |
| DOMAIN_ID | 2 — Municipal Transit Incidents |
| Hardware | MacBook Pro 13" (M2, 8GB RAM) |
| Local model | qwen2.5:3b (documented substitute for qwen3:8b due to 8GB RAM constraint) |
| Tagged commit | `1a3dbcb6e11f1b507ccfe147801376ce25949daa` |

## Part 4.3 — Schema Validation, 30 Runs (Fixed Input, turn_ceiling=6)

Fixed input: `reports/hw02/cases/schema_input.json` ("Line 22 - Bus stalled on Main St")

| Outcome over 30 runs | Count | Mean latency (ms) |
|---|---|---|
| Valid first attempt | 18 | 211,080.0 |
| Valid after 1 retry | 0 | — |
| Valid after 2+ retries | 0 | — |
| Hit turn ceiling | 12 | 273,837.2 |

**Overall mean latency across all 30 runs: 236,182.8 ms (~3.9 min/run)**

Raw data: `reports/hw02/raw/schema_raw.json` / `.csv`
Summary: `reports/hw02/raw/schema_summary.json`

### Analysis

18 of 30 runs (60%) produced a schema-compliant Planner output on the very
first attempt. Notably, **0 runs recovered after 1 or 2+ retries** — every
run that failed validation on its first attempt continued failing on every
subsequent retry until the turn ceiling was reached (12/30, 40%). This
suggests the retry mechanism's corrective feedback (the validation error
fed back into the Planner's prompt) is not effectively steering the local
3B model toward a compliant shape once it fails — it either gets the shape
right immediately or is consistently unable to self-correct within this
turn budget. A larger model, or a retry prompt with a concrete worked
example of the correct shape, would likely reduce the 40% ceiling-hit
rate.

The mean latency for runs that hit the ceiling (273.8s) is higher than for
first-attempt successes (211.1s), which makes sense: those runs make
additional Planner calls before giving up.

## Part 4.4 — Turn Ceiling Comparison, 20 Runs Each (Fixed Input)

| Ceiling | Runs | Completion rate | Mean latency (ms) | Mean latency, completed only (ms) |
|---|---|---|---|---|
| 2 | 20 | 0% | 4,050.6 | — |
| 10 | 20 | 90% | 30,163.3 | 27,295.3 |

Raw data: `reports/hw02/raw/ceiling_raw.json` / `.csv`
Summary: `reports/hw02/raw/ceiling_summary.json`

### Analysis

Ceiling=2 completed **0/20** runs — this is a structural limit, not a
model failure: reaching the Reviewer node requires at least 2 supervisor
visits (one before the Planner, one before the Reviewer), so a ceiling of
2 is exhausted before the pipeline can ever reach a review verdict. This
setting is not viable for this graph topology regardless of model quality.

Ceiling=10 completed **18/20 (90%)** of runs, at roughly 6-7x the mean
latency of the (non-functional) ceiling=2 setting, but at an acceptable
absolute cost (~27s per successful run).

**Chosen for deployment: turn_ceiling = 10.** A system that "completes"
0% of the time is not actually faster in any useful sense — it simply
fails quickly. The latency cost of ceiling=10 (about 27-30 seconds per
incident) is well within acceptable bounds for an asynchronous
tagging/summarization pipeline that does not block a user-facing request.

## Part 4.5 — Adversarial Input, 5 Runs (turn_ceiling=6)

Adversarial input: `reports/hw02/cases/adversarial_input.json` — a
multi-incident cascade report describing 6 distinct sub-events (signal
failure, two reroutes, a fare-gate malfunction, a medical emergency, and a
minor collision) bundled into a single incident report, designed to make
compressing the content into exactly 3 compliant tags difficult.

| Metric | Value |
|---|---|
| Runs | 5 |
| Ceiling hits | 5 |
| Observed ceiling-hit rate | **100% (5/5)** |

Raw data: `reports/hw02/raw/adversarial_raw.json`
Summary: `reports/hw02/raw/adversarial_summary.json`

### Analysis

The adversarial input reached the turn ceiling in all 5 runs (5/5,
exceeding the assignment's "at least 4/5" bar). This is consistent with
the schema experiment's finding that the model does not self-correct
across retries: because the input genuinely contains 6 distinct
sub-events, any 3-tag summary the model proposes is easy for the Reviewer
(or the Pydantic validator) to find fault with, and the Planner's retries
do not converge on a compliant answer within the turn budget.

**Proposed fix:** rather than asking the Planner to compress an arbitrary
number of sub-events into exactly 3 tags in one shot, a pre-processing
step could first ask the model to enumerate the distinct sub-incidents
present in the report, then either (a) explicitly instruct the Planner to
pick the 3 *most operationally significant* sub-events by a stated
criterion (e.g., service impact duration), or (b) split multi-incident
reports into separate single-incident records before tagging. Either
approach removes the structural mismatch between "one report, many
events" and "exactly 3 tags," which is likely the actual source of the
adversarial failure rather than a wording or prompt-phrasing problem.