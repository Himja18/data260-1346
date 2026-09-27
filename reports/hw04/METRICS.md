# HW4 METRICS — s1346 | Municipal Transit Incidents

## Part 3: N+1 Measurement

### Results Table
| Page size | Version | SQL stmts/req | p50 (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|---|---|
| 10 | naive | 11 | 7.76 | 11.14 | 34.93 |
| 10 | fixed | 1 | 3.94 | 6.04 | 10.43 |
| 50 | naive | 51 | 24.11 | 30.37 | 73.17 |
| 50 | fixed | 1 | 5.85 | 6.61 | 6.87 |
| 200 | naive | 201 | 87.82 | 168.36 | 224.89 |
| 200 | fixed | 1 | 12.6 | 28.46 | 40.23 |

### Speed-up Table
| Page size | p50 speed-up | p95 speed-up | p50 time saved (ms) |
|---|---|---|---|
| 10 | 1.97x | 1.84x | 3.82 |
| 50 | 4.12x | 4.59x | 18.26 |
| 200 | 6.97x | 5.92x | 75.22 |

### Why speed-up grows with page size
The naive endpoint fires one extra SQL query per incident to fetch its transit
line, so a page of N records triggers N+1 queries. The fixed endpoint uses a
LEFT OUTER JOIN and always fires exactly 1 query. At page size 10 the overhead
is 10 extra round-trips; at page size 200 it is 200. Each round-trip to MySQL
costs ~0.3-1 ms even on localhost, and those costs are additive, so the
absolute time wasted scales linearly with page size, giving a growing speed-up.

### Index: ix_incidents_category ON incidents(category)
**Before:** Q1 used type=index (full PRIMARY KEY scan, filtered=10%).
Q2 used type=ALL (full table scan of 5001 rows).
**After:** Q1 uses type=ref on ix_incidents_category (jumps to 501 Accident
rows directly). Q2 uses a covering index lookup (Using index), answering
COUNT entirely from the index without touching the table.
Q2 median latency: 1.076 ms -> 0.267 ms (4x faster).

## Part 4: RAG Evaluation

### Evaluation Table
| Q | Type | Config | Correct Retrieval | Correct Answer | Grounded | Refused When Needed |
|---|---|---|---|---|---|---|
| q1 | single_source | A_no_rag | True | True | False | True |
| q1 | single_source | B_basic_rag | True | True | True | True |
| q1 | single_source | C_context_rag | True | True | True | True |
| q2 | single_source | A_no_rag | True | True | False | True |
| q2 | single_source | B_basic_rag | True | True | True | True |
| q2 | single_source | C_context_rag | True | True | True | True |
| q3 | multi_source | A_no_rag | True | True | False | True |
| q3 | multi_source | B_basic_rag | True | True | True | True |
| q3 | multi_source | C_context_rag | True | False | True | True |
| q4 | adversarial | A_no_rag | True | True | False | True |
| q4 | adversarial | B_basic_rag | True | True | True | True |
| q4 | adversarial | C_context_rag | True | False | True | True |
| q5 | not_in_corpus | A_no_rag | N/A | False | False | False |
| q5 | not_in_corpus | B_basic_rag | N/A | False | True | False |
| q5 | not_in_corpus | C_context_rag | N/A | True | True | True |
| q6 | unrelated | A_no_rag | N/A | False | False | False |
| q6 | unrelated | B_basic_rag | N/A | False | True | False |
| q6 | unrelated | C_context_rag | N/A | True | True | True |

### k-sweep on Q1
| k | Config | Correct Answer | Note |
|---|---|---|---|
| 1 | C_context_rag | False | Single chunk above threshold, refused |
| 3 | C_context_rag | True | Optimal - correct answer with citations |
| 5 | C_context_rag | True | Correct but added minor hedge from irrelevant chunk |
