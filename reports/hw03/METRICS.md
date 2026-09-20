# METRICS.md — HW3 Part 2 Chunking Comparison

Domain 2: Municipal Transit Incidents | SID4 = 1346

## Pipeline Summary

| Pipeline | # Chunks | Time (s) | Questions Hit Expected Source | Hit Rate |
|---|---|---|---|---|
| Token-based | 117 | 9.46 | 5/5 | 100% |
| Semantic | 89 | 28.98 | 5/5 | 100% |
| Sentence-window | 1000 | 9.46 | 5/5 | 100% |

## Per-Question Results

### q1 (single_source)
**Question:** By how much, and how shortly before the accident, did Union Pacific change the warning-time thumbwheel setting at the Fox River Grove grade crossing?

**Expected source(s):** `ntsb_har9602_fox_river_grove_raw_excerpt.txt`

| Pipeline | Hit expected source? | Top-1 retrieved file | Top-1 score | Top-2 score | Top-3 score |
|---|---|---|---|---|---|
| Token-based | ✅ | `ntsb_har9602_fox_river_grove_raw_excerpt.txt` | 0.423 | 0.432 | 0.502 |
| Semantic | ✅ | `ntsb_har9602_fox_river_grove_raw_excerpt.txt` | 0.399 | 0.533 | 0.553 |
| Sentence-window | ✅ | `questions_source_mapping_notes.txt` | 0.172 | 0.298 | 0.374 |

### q2 (single_source)
**Question:** After the fatal fall at Spring Garden Station, how much did SEPTA commit to its SCOPE program, and how many outreach workers did it add?

**Expected source(s):** `ntsb_rir2203_septa_spring_garden.txt`

| Pipeline | Hit expected source? | Top-1 retrieved file | Top-1 score | Top-2 score | Top-3 score |
|---|---|---|---|---|---|
| Token-based | ✅ | `ntsb_rir2203_septa_spring_garden.txt` | 0.549 | 0.555 | 0.750 |
| Semantic | ✅ | `ntsb_rir2203_septa_spring_garden.txt` | 0.533 | 0.562 | 0.566 |
| Sentence-window | ✅ | `questions_source_mapping_notes.txt` | 0.302 | 0.460 | 0.593 |

### q3 (multi_source)
**Question:** How has the property-damage dollar threshold for a reportable non-rail transit collision changed between the FTA's 1997 SAMIS reporting guidance and its 2026 Safety & Security Policy Manual?

**Expected source(s):** `fta_samis_1997_annual_report.txt, fta_ntd_glossary_and_definitions_supplement.txt, fta_ntd_safety_security_policy_manual_2026.txt`

| Pipeline | Hit expected source? | Top-1 retrieved file | Top-1 score | Top-2 score | Top-3 score |
|---|---|---|---|---|---|
| Token-based | ✅ | `fta_ntd_glossary_and_definitions_supplement.txt` | 0.338 | 0.357 | 0.390 |
| Semantic | ✅ | `transit_incident_terminology_faq.txt` | 0.373 | 0.399 | 0.464 |
| Sentence-window | ✅ | `questions_source_mapping_notes.txt` | 0.220 | 0.316 | 0.319 |

### q4 (adversarial)
**Question:** In the WMATA Metrorail smoke and arcing incident that occurred at L'Enfant Plaza station, how many passengers were on the train and how many people were treated or transported for smoke exposure?

**Expected source(s):** `ntsb_r15-31-32_lenfant_plaza_oversight_letter.txt`

| Pipeline | Hit expected source? | Top-1 retrieved file | Top-1 score | Top-2 score | Top-3 score |
|---|---|---|---|---|---|
| Token-based | ✅ | `ntsb_r15-31-32_lenfant_plaza_oversight_letter.txt` | 0.382 | 0.597 | 0.662 |
| Semantic | ✅ | `ntsb_r15-31-32_lenfant_plaza_oversight_letter.txt` | 0.400 | 0.613 | 0.617 |
| Sentence-window | ✅ | `ntsb_recommendations_status_wmata_history.txt` | 0.295 | 0.442 | 0.448 |

### q5 (single_source)
**Question:** What was the specific mechanical cause of the failure that allowed the Miami International Airport automated people mover train to collide with the terminal wall in 2008, and what safety system should have prevented it but did not?

**Expected source(s):** `ntsb_rar1101_miami_apm_verified.txt`

| Pipeline | Hit expected source? | Top-1 retrieved file | Top-1 score | Top-2 score | Top-3 score |
|---|---|---|---|---|---|
| Token-based | ✅ | `ntsb_rar1101_miami_apm_verified.txt` | 0.324 | 0.439 | 0.494 |
| Semantic | ✅ | `ntsb_rar1101_miami_apm_verified.txt` | 0.318 | 0.532 | 0.600 |
| Sentence-window | ✅ | `ntsb_rar1101_miami_apm_verified.txt` | 0.337 | 0.383 | 0.470 |

## Adversarial Question Deep-Dive

### q4

**Token-based** — hit expected source: True
  - rank 1, score 0.3819, file `ntsb_r15-31-32_lenfant_plaza_oversight_letter.txt`: NTSB Safety Recommendation Letter R-15-31 and R-15-32 (Urgent) Date: September 30, 2015. To: The Honorable Anthony Foxx, Secretary of Transportation, ...
  - rank 2, score 0.5968, file `ntsb_recommendations_status_wmata_history.txt`: NTSB WMATA Safety Recommendation History and Status - Cross-Reference Compilation Compiled from references within NTSB accident reports and safety rec...
  - rank 3, score 0.6620, file `ntsb_rar1002_fort_totten.txt`: Train 112, operating in automatic mode, was traveling behind train 214. According to recorded train control system data, the speed commands transmitte...

**Semantic** — hit expected source: True
  - rank 1, score 0.4000, file `ntsb_r15-31-32_lenfant_plaza_oversight_letter.txt`: NTSB Safety Recommendation Letter R-15-31 and R-15-32 (Urgent) Date: September 30, 2015. To: The Honorable Anthony Foxx, Secretary of Transportation, ...
  - rank 2, score 0.6132, file `ntsb_recommendations_status_wmata_history.txt`: 2009 (June 22): Fort Totten collision (RAR-10/02) -- a track circuit failure caused loss of train detection, leading one train to strike a stopped tra...
  - rank 3, score 0.6168, file `transit_incident_terminology_faq.txt`: A: Because the count depends on when the statement was made and what is being counted. The 1996 Shady Grove report references prior WMATA investigatio...

**Sentence-window** — hit expected source: True
  - rank 1, score 0.2952, file `ntsb_recommendations_status_wmata_history.txt`: 2015 (January 12): L'Enfant Plaza smoke/arcing incident -- an electrical short circuit near the third rail filled a tunnel and station with smoke; one...
  - rank 2, score 0.4416, file `ntsb_r15-31-32_lenfant_plaza_oversight_letter.txt`: The smoke originated from an arcing event near the third rail about 2,000 feet south of the L'Enfant Plaza station. ...
  - rank 3, score 0.4481, file `ntsb_r15-31-32_lenfant_plaza_oversight_letter.txt`: Subject: WMATA Metrorail smoke and arcing accident, L'Enfant Plaza station, January 12, 2015, and inadequate safety oversight by the Tri-State Oversig...

