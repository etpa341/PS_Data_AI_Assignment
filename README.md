# Kestrel Data & AI Challenge: Evan Thapa

**Start with [deliverables/](deliverables/README.md):** the report, the final dataset, the data quality report, the evaluation summary, the data dictionary, the AI usage log, the appendix, the governance workbook and the prompt in one folder. If the markdown looks raw, read [deliverables/report.pdf](deliverables/report.pdf). The rest of this repo is how it was built.

A reproducible Python pipeline turns the 52 dealer feedback files into one cleaned, validated and redacted table; every row keeps its source file, sheet and row.
Claude Haiku 5.5 labels each customer comment with themes and sentiment, measured against 120 blind hand labels plus sanity, spot and extra checks.
The answers to the three business questions are in [report.md](report.md) ([PDF](docs/report.pdf)); supporting detail is in [docs/appendix.md](docs/appendix.md).

**Headline answers** (copied from [report.md, section 1](report.md#1-headline-answers)):

- **Q1. Where and why (confidence: medium to high).** Service is the problem: 27.2% of Service responses are dissatisfied, against 16.2% in Parts and 10.1% in Sales. The leading complaints are not being kept informed (28% of dissatisfied comments) and waiting (24%). In Parts the main complaint is waiting (47%). In Sales it is staff (34%).
- **Q2. What changed (medium).** Dissatisfaction rose from 18.9% to 24.4% (Oct to Dec 2025 against Jul to Sep 2026, 21 dealers). Most of the rise is at Parramatta and Dandenong, which stayed high from May while the other 19 dealers fell back to about 20% to 25%. Without those two, the rise is +2.4 points and not statistically significant.
- **Q3. What to fix first and what it is worth (high on the ranking, low on the dollars).** Under stated assumptions, about $2.5m a year of Service and Parts revenue is at risk (range $1.2m to $7.2m). Communication ($0.71m) and waiting ($0.65m) come first. There is no churn data, so the dollars are an estimate. The ranking does not depend on the assumed leave rate.

**Start here**

1. [report.md](report.md) or [docs/report.pdf](docs/report.pdf): findings, recommendations and limits.
2. [docs/appendix.md](docs/appendix.md): full data-quality table, evaluation detail and short notes cut from the report.
3. Evidence: [ai_usage_log.md](ai_usage_log.md) (what AI did, how it was checked, where it was wrong) and [profiling/data_governance.xlsx](profiling/data_governance.xlsx) (manifest, issues log, decisions D1 to D9, data requests).

**Repo map** (everything is committed unless marked gitignored)

| Path | What it holds |
|---|---|
| `deliverables/` | Copies of the final report (PDF and markdown), chart, gold dataset, quality report, evaluation summary, data dictionary, AI usage log, appendix, governance workbook and prompt, built by `make_deliverables.py` |
| `config/` | Per-file parsing rules, model and price settings, hashed staff names for redaction |
| `data/silver/`, `data/silver_labels/`, `data/gold/` | Cleaned table; AI labels with the answer cache and run logs; gold table and revenue panel |
| `data/bronze/` | Every row as read, unredacted: **gitignored**, rebuilt by `01_bronze.py` |
| `feedback/` | The 52 source files (raw personal data): **gitignored**, place here to rerun |
| `reference/` | Dealer list and monthly revenue from the pack |
| `docs/` | `appendix.md`, `report.pdf` (generated from `report.md`) and `original_brief.md` (the original task brief) |
| `labelling/` | Hand-labelling sheets (blank and filled), extra check, progress files |
| `outputs/` | Every analysis output: tables, evaluation, sanity checks, figures, rule log, fact pack |
| `profiling/` | `profile.py` and `data_governance.xlsx` |
| `prompts/` | `classify_v1.txt` and its build record |
| `tests/` | Pipeline tests (fake client, no API calls) |
| `01_bronze.py` to `05_gold.py` | Numbered pipeline: read, clean and redact, label, evaluate, join |
| `analysis.ipynb`, other `*.py` | Q1 to Q3 analysis; helpers for model choice, prompt, figures, PDF, checks |
| `SPEC.md`, `data_dictionary.md` | Build specification; columns of every table and output |
| `.env` | API key for live labelling only: **gitignored**, never committed |

**Where to find what the brief asks for**

| Brief asks for | Where |
|---|---|
| Approach and assumptions | [report.md section 7](report.md#7-approach-trust-and-ai-use); assumptions in [section 5](report.md#5-what-to-fix-first-and-what-it-is-worth-q3) and the decisions log in [profiling/data_governance.xlsx](profiling/data_governance.xlsx) |
| Tech choices | [report.md section 7](report.md#7-approach-trust-and-ai-use) |
| Data quality | [report.md section 6](report.md#6-data-quality); full table in [docs/appendix.md](docs/appendix.md#a-data-quality-the-10-issue-groups) |
| Business answers | [report.md sections 1](report.md#1-headline-answers), [3](report.md#3-what-drives-negative-feedback-q1), [4](report.md#4-change-over-the-year-q2) and [5](report.md#5-what-to-fix-first-and-what-it-is-worth-q3) |
| Recommendations | [report.md section 2](report.md#2-recommendations) |
| AI usage | [ai_usage_log.md](ai_usage_log.md); summary in [report.md section 7](report.md#7-approach-trust-and-ai-use) |
| Consolidated dataset | [data/gold/](data/gold/) (columns in [data_dictionary.md](data_dictionary.md)); it includes the 201 excluded rows, flagged in `excluded` with the reason in `exclude_reason`, and the 7,070 included rows (7,060 with a score) are the ones used in the analysis |

**Report:** [report.md](report.md) ([PDF: docs/report.pdf](docs/report.pdf)), with detail in [docs/appendix.md](docs/appendix.md). Q2 chart: [outputs/figures/q2_dissatisfied_by_group.png](outputs/figures/q2_dissatisfied_by_group.png).

## Reproduce

The committed label cache (`data/silver_labels/cache.jsonl`) lets the whole pipeline rerun offline with no API key.

Steps 8b to 11 (chart, PDF, fact pack, deliverables copy) are optional and not needed to reproduce the analysis.

- Place the source `feedback/` folder (the 52 files from the pack) in the repo root, next to `reference/`. The scripts read it read-only. `feedback/` is gitignored (raw personal data) and is never committed. The label cache (`data/silver_labels/cache.jsonl`) is committed, so the whole pipeline reruns offline with no API key.
- `pip install -r requirements.txt` (Python 3.13; versions pinned as used; `anthropic` is optional and only needed for a live labelling run), then from the repo root:
  1. `python 01_bronze.py` - read every file and sheet
  2. `python 02_silver.py` - clean, redact, validate (`outputs/quality_report.md`)
  3. Only before a new live run, with `ANTHROPIC_API_KEY` set: `python select_model.py` picks the newest Haiku available to the key and records it in `config/settings.yaml`; `python build_prompt.py` writes `prompts/classify_v1.txt` from the Definitions tab (it refuses to change an existing version). An offline rerun skips this step: model and prompt are already recorded.
  4. `python 03_label.py` - AI labels from the cache (offline by default; `--live` calls the API, add `--workers 8` for parallel calls; `--dry-run` uses a fake client, `--estimate` prints calls and cost). The key is read from `ANTHROPIC_API_KEY` or the gitignored `.env`.
  5. `python 04_evaluate.py --sheet labelling/labelling_sheet_filled.xlsx` - AI labels vs hand labels, plus the Ringwood D2 test (`outputs/evaluation/`)
  6. `python 05_gold.py` - silver + labels + revenue (`data/gold/`)
  7. `analysis.ipynb` - Q1-Q3, top to bottom. Its outputs are saved; to re-execute under Jupyter: `python -m nbconvert --to notebook --execute --inplace analysis.ipynb` (needs the optional `nbconvert` and `ipykernel` in `requirements.txt`).
  7b. `python evaluate_definitions.py` - the V2 check: do the "dissatisfied" and "at risk" cutoffs agree with the AI sentiment at least as well as the alternatives, and do dealer rankings change between them (`outputs/evaluation/v2_*.csv`). Run after step 7.
  8. `python derived_numbers.py` - counts the report quotes from other outputs (`outputs/derived_numbers.csv`). Report: `report.md`, detail in `docs/appendix.md`.
  8b. `python make_figures.py` - draws `outputs/figures/q2_dissatisfied_by_group.png` from `outputs/q2_monthly_by_group.csv` (run before step 9; the report embeds it).
  9. `python make_report_pdf.py` - renders `report.md` to `docs/report.pdf` (A4, 11pt, 2 cm margins; headless Edge or Chrome). `docs/report.pdf` is generated from `report.md`: edit the markdown, then rerun this, never the PDF.
  10. `python make_fact_pack.py` - writes `outputs/report_fact_pack.md`, source facts for writing the report, every number with its source file.
  11. `python make_deliverables.py` - last step: rebuilds `deliverables/`, copies of the final files (see `deliverables/README.md`). Run it after the report and PDF are final; it stops if `docs/report.pdf` is older than `report.md`.
  - Tests: `python -m pytest -q tests` (fake client and dummy data; no API calls).
- Staff names are redacted from the staff-column list (any letter case) plus reviewed names not in any staff column, kept only as hashes in `config/redaction.yaml`. Redaction is best effort.
- `data/bronze/` is gitignored: it holds unredacted comment text and the staff-name list. It is rebuilt by `01_bronze.py`. Redacted data starts at `data/silver/`.
- Design and decisions: `SPEC.md`, `config/file_mappings.yaml`, `profiling/data_governance.xlsx` (Decisions_Log). Quality report: `outputs/quality_report.md`.
- Hand labels: `python make_labelling_sheet.py` builds `labelling/labelling_sheet.xlsx` (it refuses to overwrite an existing sheet). The theme definitions in its Definitions tab, as edited by the labeller, are the single source for the definitions in `prompts/classify_v1.txt`, so the model is judged against the same definitions used for labelling.
- Spot check: `python make_spot_check.py` writes `outputs/spot_check.xlsx`, with 10 silver rows (one each from Geelong 2025, Liverpool Q3, Ringwood Q2, a corrected Shepparton row and a Bendigo "S" row, plus 5 random, seed 42) and empty pass_fail and notes columns for checking against the source files. It refuses to overwrite.
- Extra hand check: `python make_extra_check.py` builds `labelling/extra_check.xlsx` (AI-labelled Vehicle or product and Other comments, which the 120-row sample never contained; no AI columns; refuses to overwrite). Once it is labelled, `python evaluate_extra_check.py` scores the AI on it (`outputs/evaluation/extra_check_*`).

### Known limits

- **Noosa (QLD05) has no rows in the labelled sample.** The 120-row sample uses a strict proportional split by dealer and department. Noosa has 37 of the 5,150 customer-voice comments (0.7%), which is not enough for a share of 120 in any department, so AI label accuracy is not measured on Noosa comments. This was kept by choice, so as not to over-sample small dealers.
