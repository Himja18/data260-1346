# SOURCES.md — HW3 Part 2 Corpus

**Domain 2: Municipal Transit Incidents** · SID4 = 1346 · Accessed: 2026-09-19

All primary sources are public-domain works of the U.S. federal government (NTSB, FTA, UMTA).
Each file below was either (a) fetched live from the government source URL listed, or (b) compiled
from facts found inside one or more of those live-fetched files, in which case it is marked
**[DERIVED]** and lists which primary file(s) it draws from instead of an independent URL.

## Primary source documents (independently fetched)

| File | Title | Source URL | Accessed |
|---|---|---|---|
| `ntsb_har9602_fox_river_grove.txt` + `_raw_excerpt.txt` | NTSB/HAR-96/02 — Collision of METRA Train and School Bus, Fox River Grove, IL (1995) | https://www.ntsb.gov/investigations/AccidentReports/Reports/HAR9602.pdf | 2026-09-19 |
| `ntsb_har0103_conasauga.txt` + `_raw_excerpt.txt` | NTSB/HAR-01/03 — Collision of CSXT Freight Train and School Bus, Conasauga, TN (2000) | https://www.ntsb.gov/investigations/AccidentReports/Reports/HAR0103.pdf | 2026-09-19 |
| `ntsb_rar9604_shady_grove.txt` | NTSB/RAR-96/04 — WMATA Train T-111 Collision, Shady Grove, MD (1996) | https://www.ntsb.gov/investigations/AccidentReports/Reports/rar9604.pdf | 2026-09-19 |
| `ntsb_rar1002_fort_totten.txt` + `_raw_excerpt.txt` + `ntsb_fort_totten_upgrade_programs_excerpt.txt` | NTSB/RAR-10/02 — WMATA Metrorail Collision, Fort Totten, DC (2009) | https://www.ntsb.gov/investigations/accidentreports/reports/rar1002.pdf | 2026-09-19 |
| `ntsb_r15-31-32_lenfant_plaza_oversight_letter.txt` | NTSB Urgent Safety Recommendation Letter R-15-31/R-15-32 (L'Enfant Plaza / WMATA oversight, 2015) | https://www.ntsb.gov/safety/safety-recs/recletters/R-15-031-032.pdf | 2026-09-19 |
| `ntsb_rir2519_nj_transit_tree.txt` | NTSB RIR-25-19 — NJ Transit Light Rail Vehicle Collision with Tree, Florence, NJ (2024) | https://www.ntsb.gov/investigations/AccidentReports/Reports/RIR2519.pdf | 2026-09-19 |
| `ntsb_rir2203_septa_spring_garden.txt` | NTSB RIR-22/03 — SEPTA Fatality at Spring Garden Station, Philadelphia, PA (2021) | https://www.ntsb.gov/investigations/AccidentReports/Reports/RIR2203.pdf | 2026-09-19 |
| `ntsb_hab1810_nyc_transit_bus_pedestrian.txt` | NTSB HAB-18/10 — Fatal Pedestrian Collision with NYC Transit Bus (2016) | https://www.ntsb.gov/investigations/AccidentReports/Reports/HAB1810.pdf | 2026-09-19 |
| `ntsb_rar1501_cta_ohare_fatigue.txt` | NTSB/RAR-15-01 — CTA Train Collision at O'Hare Station, Chicago, IL (2014) | https://www.ntsb.gov/investigations/accidentreports/reports/rar1501.pdf | 2026-09-19 (verified live fetch) |
| `ntsb_rar1101_miami_apm_verified.txt` | NTSB/RAR-11/01 — Miami Intl. Airport Automated People Mover Collision (2008) | https://www.ntsb.gov/investigations/AccidentReports/Reports/RAR1101.pdf | 2026-09-19 (verified live fetch) |
| `fta_ntd_safety_security_policy_manual_2026.txt` + `_part2.txt` | National Transit Database Safety & Security Policy Manual, January 2026 | https://www.transit.dot.gov/sites/fta.dot.gov/files/2026-01/2026%20Safety%20&%20Security%20Manual_V1.pdf | 2026-09-19 |
| `fta_samis_1997_annual_report.txt` + `fta_samis_1997_detailed_tables.txt` | SAMIS 1997 Annual Report (FTA-MA-26-5002-99-01) | https://www.transit.dot.gov/sites/fta.dot.gov/files/docs/samis97.pdf | 2026-09-19 |
| `fta_ntst_2021_summaries_trends.txt` | 2021 National Transit Summaries & Trends (NTST) | https://www.transit.dot.gov/sites/fta.dot.gov/files/2022-11/2021%20National%20Transit%20Summaries%20and%20Trends_1-1.pdf | 2026-09-19 |
| `fta_transit_bus_accident_investigations_2022.txt` | FTA Report No. 0222 — Transit Bus Accident Investigations: Background Research (2022) | https://rosap.ntl.bts.gov/view/dot/64104/dot_64104_DS1.pdf | 2026-09-19 |
| `umta_emergency_preparedness_guidelines_1992.txt` | UMTA — Recommended Emergency Preparedness Guidelines for Rail Transit Systems (1992) | https://ntlrepository.blob.core.windows.net/lib/6000/6700/6752/609.html | 2026-09-19 |

## Derived / cross-reference files [DERIVED]

These files do not have their own independent source URL. They synthesize or index facts that
already appear in the primary source files above; each one names, in its own header, which
primary document(s) it draws from.

| File | Drawn from |
|---|---|
| `fta_ntd_glossary_and_definitions_supplement.txt` | FTA NTD Policy Manual, SAMIS 1997, NTST 2021 |
| `ntsb_recommendations_status_wmata_history.txt` | Fox River Grove, Shady Grove, Fort Totten, L'Enfant Plaza letter |
| `ntsb_organization_and_investigation_process.txt` | All NTSB report files in this corpus |
| `transit_incident_terminology_faq.txt` | All FTA/NTSB files in this corpus |
| `questions_source_mapping_notes.txt` | All files in this corpus (working notes for `questions.yaml`) |
| `ntsb_r09-08_mbta_newton_ptc_context.txt` | Citations found inside `ntsb_rar1501_cta_ohare_fatigue.txt` (not an independent fetch of the Newton, MA report itself) |
| `corpus_index_and_coverage_notes.txt` | Full corpus index/summary |
| `final_corpus_summary.txt` | Full corpus index/summary |

## Integrity note

During assembly, four files were found to have been created without a corresponding verified
fetch earlier in the working session (covering a Hamden, CT battery-bus fire; and earlier drafts of
the Miami APM, CTA O'Hare, and a roadway-worker-protection report). All four were deleted
immediately on discovery. Two of those topics (Miami APM, CTA O'Hare) were independently
re-researched and re-fetched with tool-confirmed live retrieval, and are the two entries above
marked "(verified live fetch)." See `corpus_index_and_coverage_notes.txt` for full detail.
