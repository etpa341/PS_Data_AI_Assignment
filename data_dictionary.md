# Data dictionary

Layers in run order: bronze → silver → silver_labels → gold. Personal data columns (customer name, phone, email, rego, customer number, record ids, staff) are dropped when bronze reads the files and never written anywhere (SPEC section 8).

## data/bronze/ (gitignored: holds unredacted comment text)

`bronze_rows.csv`: one row per non-blank source row.

| Column | Meaning |
|---|---|
| source_file, source_sheet, source_row | Where the row came from (sheet `(csv)` for CSV files; row is 1-based as in Excel) |
| family | File family in `config/file_mappings.yaml` |
| block | Template block within a sheet (Frankston and Ringwood Q1 change header partway down) |
| row_class | `data`, `header`, `banner` (title rows above the header), `total` (monthly totals), `note` (footer notes) |
| date_raw, department_raw, rating_raw, comment_raw | Cell text exactly as read |
| site_raw, vehicle_raw, action_raw, channel_raw, month_raw | Other mapped columns, as read |
| rating_column | Header of the rating column (decides the scale, e.g. Ringwood "Score (out of 10)") |
| counts_raw | Toowoomba Q4 summary only: JSON of response counts by rating |
| note_text | Text of non-data rows |
| raw_row_hash | 16-hex SHA-256 of the full source row including dropped columns; used only to find exact duplicates |

`bronze_sheets.csv`: one row per file and sheet with row-class counts, PII cells dropped, sheet content hash, status and any error. `staff_names.csv`: staff first names from the staff columns, used to redact names in comments.

## data/silver/feedback_silver.csv

One row per bronze data row (7,271). Excluded rows stay in the table.

| Column | Meaning |
|---|---|
| feedback_id | `<dealer_code>-<10 hex>`: hash of source file, sheet and row; stable across runs |
| source_file, source_sheet, source_row | Lineage back to the source cell |
| dealer_code | From `reference/dealerships.csv`; North QLD rows from the Site column; Hunter and IPS by alias (D8) |
| department | Sales, Service, Parts or Unknown |
| date_raw | Date cell as recorded |
| feedback_date | Parsed date (ISO); empty when unparseable or vague |
| date_corrected | True on the 6 Shepparton rows moved back one year (D4) |
| month | YYYY-MM from the row date (never the tab name); month-only for 10 vague Ipswich dates (D7) |
| rating_raw | Rating as recorded (number, label, or stars) |
| rating_scale | `num_1_5`, `num_1_10`, `labels_1_5`, `labels_bad_ok_good`, `stars_1_5` |
| score_norm | (x - min) / (max - min) × 100 on the true scale, after the Geelong 2025 fix (D1) |
| dissatisfied | score_norm < 40 (1-2 of 5, 1-4 of 10, Tamworth Bad); empty when no score |
| at_risk | score_norm ≤ 50 (≤3 of 5, ≤5 of 10, Tamworth OK or Bad); empty when no score |
| comment_clean | Comment with `[EMAIL]`, `[PHONE]`, `[REGO]`, `[NAME]` (customer-name prefix) and `[STAFF]` redactions |
| has_text | Comment contains letters |
| voice | `customer`, `staff_paraphrased` (third-person write-up by staff), `unknown` (no text) |
| dept_inferred | True on Bendigo "S" rows mapped to Sales (D3) |
| dq_flags | Semicolon list, e.g. `pii_redacted`, `staff_name_redacted`, `dealer_alias`, `rating_inverted_fixed`, `date_year_corrected`, `date_vague_month_inferred`, `exact_duplicate`, `cross_tab_duplicate`, `test_row`, `rating_missing`, `dept_inferred` |
| excluded | True if the row is left out of analysis |
| exclude_reason | Why (references the decision or issue id) |

## data/silver_labels/ (written by 03_label.py)

`labels.csv`: one row per silver row.

| Column | Meaning |
|---|---|
| feedback_id | Join key to silver |
| label_status | `labelled`, `no_comment`, `skipped_voice`, `skipped_excluded`, `failed_validation`, `not_in_cache` |
| primary_theme, secondary_theme | One of the 8 themes (SPEC section 9); secondary optional |
| sentiment | positive, neutral, negative, mixed |
| confidence | Model's own 0-1 confidence (not calibrated) |
| model, prompt_version, prompt_sha | What produced the label; prompt_sha detects prompt edits without a version bump |
| run_date | Date the label was obtained (from the cache entry) |
| cache_key | sha256(redacted text + prompt version + model) |
| attempts | 1, or 2 after one retry |
| error | Validation error when label_status = failed_validation |

`cache.jsonl`: one JSON line per cache key with the raw responses, so the pipeline reruns offline. `run_log.json`: counts for the last run (offline reruns overwrite it). `run_history.jsonl`: one line per live run, with token usage. `run_log_live_full_2026-10-28.json`: the full live run's log, saved from its console output.

## data/gold/ (written by 05_gold.py)

`feedback_gold.csv`: silver columns plus the label columns above.

`dealer_month_dept.csv`: 24 dealers × 12 months × 3 departments.

| Column | Meaning |
|---|---|
| dealer_code, month, department | Grain |
| transactions | vehicles_sold / service_jobs / parts_transactions from monthly_revenue.csv |
| revenue_aud | sales / service / parts revenue from monthly_revenue.csv |
| responses, rated | Included feedback rows, and those with a score. **Empty (missing) in gap cells**, 0 only when the dealer-month has feedback but not this department |
| dissatisfied_n, at_risk_n, dissatisfied_share, at_risk_share, mean_score | From rated rows |
| with_text, ai_labelled | Rows with comment text, and with a valid AI label |
| gap_reason | Set for dealer-months with no feedback: D5 gaps (Penrith 2026-06, Toowoomba 2025-10..12) and Shepparton after closure |

## Outputs

`outputs/quality_report.md`, `dq_rule_log.csv`, `exclusions.csv`, `bronze_reconciliation.csv`, `sentiment_check_pools.csv`; `outputs/evaluation/` (04_evaluate.py); `outputs/charts/`, `q2_robustness.csv` (Q2 rise with and without Ringwood, dealer-clustered intervals, leave-one-dealer-out) and `q2_dealer_drivers.csv` (each dealer's contribution to the Q2 change) from analysis.ipynb.

Also from analysis.ipynb:
- `sanity/`: `label_status.csv`, `theme_distribution.csv`, `sentiment_vs_dissatisfied.csv` (checks on the full labelled set).
- Q1: `q1_by_department.csv`, `q1_by_dealer.csv`, `q1_by_dealer_department.csv` (dissatisfied share with n and Wilson CI); `q1_theme_by_department.csv` (theme share of dissatisfied customer comments; basis primary / any mention; all dealers / without Essendon and Ipswich), `q1_theme_by_dealer.csv`, `q1_theme_by_dealer_department.csv` (`thin` = n < 30).
- Q2: `q2_monthly.csv`, `q2_without_dealers.csv`, `q2_collection_check.csv`, `q2_booking_themes.csv` (booking keywords and the Process and facilities label, before and after May 2026).
- Q3: `q3_revenue_at_risk.csv`, `q3_cells.csv`, `q3_sensitivity_headline.csv`, `q3_sensitivity_sales.csv`; `q3_theme_split.csv` ($m by theme, headline and indicative Sales line, with and without Essendon and Ipswich), `q3_theme_split_cells.csv` (per cell, with `mix_source`), `q3_priority.csv` (frequency, severity, proposed fixability, rank).
- `evaluation/extra_check_rows.csv`, `extra_check_summary.csv`, `extra_check_report.md` (from `evaluate_extra_check.py`): blind hand check of AI-labelled Vehicle or product and Other comments; per-row agreement, precision per theme with Wilson CI, and every disagreement with its redacted text.
- `spot_check.xlsx` (from `make_spot_check.py`): 10 silver rows with source location and parsed values, plus empty pass_fail and notes columns for a manual check against the source files.
- Fact-pack tables (analysis.ipynb): `q2_monthly_by_group.csv` (monthly n, dissatisfied share, mean score for Parramatta, Dandenong and the other 19 like-for-like dealers), `q2_change_by_department.csv`, `revenue_context.csv` (revenue, units, average value by department), `q3_by_dealer.csv` (headline and Sales line by dealer), `q1_bendigo_s_sensitivity.csv`, `theme_example_quotes.csv` (one 4-12 word redacted comment per theme).
- `../deliverables/` (from `make_deliverables.py`): copies of the final report, chart, gold dataset, quality report, evaluation summary and this dictionary; each file's source is listed in `deliverables/README.md`.
- `evaluation/v2_sentiment_by_score.csv`, `v2_cutoff_agreement.csv`, `v2_rank_comparison.csv` (from `evaluate_definitions.py`): the V2 check of the dissatisfied and at-risk cutoffs: AI sentiment at each score level; precision, recall and F1 of four cutoffs against AI negative and negative-or-mixed; and each dealer's rank by dissatisfied share and by at-risk share.
- `report_fact_pack.md` (from `make_fact_pack.py`): source facts for the report, each number with its source file.
- `figures/q2_dissatisfied_by_group.png` (from `make_figures.py`): monthly dissatisfied share for Parramatta, Dandenong and the other 19 like-for-like dealers, from `q2_monthly_by_group.csv`, with a line at 5 May 2026; embedded in report.md.
- `relabel_redaction_fix.csv`: the 152 comments relabelled after the staff-name redaction fix, with primary, secondary and sentiment before and after (no text).
- `q2_parramatta_themes.csv`: Parramatta theme shares of dissatisfied comments before vs from May 2026 (primary and any mention, n, change in points).
- `derived_numbers.csv` (from `derived_numbers.py`): counts the report quotes that are computed over other outputs (metric, value, source, method), incl. staff first names left in comment text (counts only) and the 5 May banner cell.
- `d2_ringwood_sensitivity.csv`, `labelling_sample_coverage.csv`. From 03_label.py: `label_cost_estimate.json` (estimate made before the run).
