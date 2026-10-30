# HW8 METRICS - Himja Patel (s1346)

| SID4 | PORT_BASE | PREFIX | SEED | VERIFY_SEED | DOMAIN_ID | Model | Hardware |
|---|---|---|---|---|---|---|---|
| 1346 | 8446 | s1346 | 1346 | 261346 | 2 (Municipal Transit Incidents) | qwen2.5:3b via Ollama | MacBook Pro 13" (Apple M2, 8 GB RAM), macOS |

## Part 1 - Request/response over Kafka

| Operation | correlation_id | success | result | correlation preserved | round trip (ms) |
|---|---|---|---|---|---|
| CREATE_INCIDENT | `4873e764-661f-4182-a43b-03378e21cbb3` | True | incident_id `05c8fc63-1fb9-4502-830e-eccc16713a92` | True | 27.6 |
| GET_INCIDENT | `297abe88-364a-4b5d-bb8a-7b30166b0630` | True | fields round-trip: True | True | 13.7 |

| Error case | success | error | correlation preserved |
|---|---|---|---|
| unknown_incident_id | False | Incident not found | True |
| unknown_operation | False | Unknown operation | True |
| missing_and_invalid_fields | False | Validation failed: route_title must not be empty; location is required; category must be one of Delay, Breakdown, Accident, Service Change; passengers_affected Input should be greater than or equal to 0 | True |

## Part 2 - Three-agent pipeline

| correlation_id | status | end-to-end (s) | stages in trace | reviewer notes |
|---|---|---|---|---|
| `30f19a64-7432-4fbf-b85c-9d427d48b28f` | approved | 26.8 | you -> planner -> writer -> reviewer | Draft answers the question and follows the plan |
| `e1fa1092-6f57-41a3-9adf-f6f26e0a6eea` | approved | 25.69 | you -> planner -> writer -> reviewer | Draft answers the question and follows the plan |

## Part 3 - Failure behaviour

| Failure scenario | Before fix | After fix |
|---|---|---|
| Duplicate delivery (same correlation_id sent twice) | no idempotency: processed 2x, **2 drafts** | correlation_id store: processed 1x, skipped 1, **1 draft** |
| Consumer killed mid-work (SIGKILL during 8 s of work) | auto-commit: committed offset 34 > message offset 33 at kill, redelivered=False, **LOST** | commit after success: committed offset 25 = message offset 25 at kill, redelivered=True, committed 26 after restart, **completed after restart** |
| Poison message (invalid JSON, then JSON without `plan`) | no retry/DLQ: writer crashed 2x on the same offset, good message processed=False (**partition blocked**) | 3 attempts each -> **2 records in s1346_dead_letter**, 2/2 good messages processed |
| Two partitions / two consumers (20 msgs, 4 incidents) | no key: **1/4 incidents in order**, 5 inversions | key = incident id: **4/4 in order**, 0 inversions, each incident in one partition |

### Ordering detail (VERIFY_SEED 261346)

| Run | Incident | Partitions used | Processed seq | In order |
|---|---|---|---|---|
| unkeyed | INC-870109 | [0, 1] | [1, 2, 3, 4, 5] | yes |
| unkeyed | INC-464751 | [0, 1] | [2, 1, 3, 4, 5] | NO |
| unkeyed | INC-322480 | [0, 1] | [2, 3, 1, 5, 4] | NO |
| unkeyed | INC-189756 | [0, 1] | [1, 2, 3, 5, 4] | NO |
| keyed | INC-464751 | [0] | [1, 2, 3, 4, 5] | yes |
| keyed | INC-322480 | [1] | [1, 2, 3, 4, 5] | yes |
| keyed | INC-870109 | [0] | [1, 2, 3, 4, 5] | yes |
| keyed | INC-189756 | [1] | [1, 2, 3, 4, 5] | yes |

## verification.json

15/15 checks passed (full) on commit `f9aaabdb243f`

| Check | Result |
|---|---|
| section0_config | PASS |
| offline_test_suite | PASS |
| kafka_broker_reachable | PASS |
| topics_exist_with_partitions | PASS |
| create_incident_over_kafka | PASS |
| get_incident_round_trip | PASS |
| error_get_unknown_id | PASS |
| error_unknown_operation | PASS |
| error_invalid_fields | PASS |
| duplicate_replay_idempotent | PASS |
| fastapi_on_port_base | PASS |
| fastapi_create_get_via_kafka | PASS |
| fastapi_unknown_id_404 | PASS |
| pipeline_inbox_to_final | PASS |
| poison_to_dead_letter | PASS |
