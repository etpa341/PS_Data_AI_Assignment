# Appendix to the report

Detail moved out of `report.md`. Every number cites its output file.

## A. Data quality: the 10 issue groups

The 161 issues in `profiling/data_governance.xlsx` (Issues_Log: 70 High, 61 Medium, 30 Low) fall into 10 groups. Row counts come from `outputs/dq_rule_log.csv` (rule id in brackets) and `outputs/exclusions.csv`.

| # | Issue group | Issues | Rows affected | Action |
|---|---|---|---|---|
| 1 | Personal data (name, phone, email, rego and customer-number columns; contact details inside comments) | 84 | 9,604 PII cells dropped at read time (R12); 765 comments redacted (R11); 805 comments with staff first names replaced (R11b; 652 before the fix of 2026-10-28). Before that fix, 152 included comments still held a staff first name: 81 listed names in another case, because the match was case-sensitive, and 71 with one of 4 unlisted names (`outputs/derived_numbers.csv`) | Fix: dropped and redacted before storage. Customer contact patterns and staff names: 0 remain, with staff names checked token by token, independent of the redaction code. Redaction is best effort |
| 2 | File layout (banner rows, semicolon CSVs, Windows-1252 encoding, mid-sheet template changes, total rows, footer notes, an empty tab) | 17 | All 82 sheets read; 13 total rows and 2 notes kept in bronze as non-data (`outputs/quality_report.md`) | Fix: parse each file family with its own settings |
| 3 | Dates (US order in Liverpool Q3, 2-digit years, Excel serials, vague dates, Shepparton dated after closure, Penrith June tab dated July) | 11 | 6 Shepparton rows moved back a year (R05, D4); 10 vague Ipswich dates given month only (R04, D7); 43 rows outside their tab's period (R06) | Fix and flag |
| 4 | Rating scales (text labels, stars, Bad/OK/Good, 1-10 at Ringwood, Geelong 2025 reversed, missing) | 9 | 5 scales (R07); 68 Geelong rows reversed (R09, D1); 11 missing ratings (R08) | Fix: 0-100 on the true scale. The ratings-vs-wording check finds no reversed scale after the fix; 23 of 25 file pools testable, covering 22 of 24 dealers (R10, `outputs/sentiment_check_pools.csv`) |
| 5 | Duplicates and copies | 9 | 16 exact duplicates (R17; all 12 at Springwood sit directly below their copy); 12 Essendon Sales copies of Service rows (R19, D6); 112 Chermside rows superseded by FINAL v2; 43 Penrith June rows copied from July (R15) | Exclude |
| 6 | Not dealer feedback (copied Google reviews, an aggregate summary, test rows) | 3 | 8 + 6 + 4 rows (R15, R16) | Exclude |
| 7 | Departments (Bendigo codes, a missing department column, departments almost absent) | 6 | 32 Bendigo "S" rows → Sales, flagged as inferred (R14, D3) | Fix and flag; ask Bendigo (R4) |
| 8 | Dealer mapping and coverage (alias names, gaps, Noosa's low volume, record IDs reused across dealers) | 15 | 580 rows mapped by alias (R02, D8); gaps for Penrith June 2026 and Toowoomba Oct-Dec 2025 (D5) | Flag; data requests R1-R3, R5 |
| 9 | Staff write-ups rather than the customer's own words | 6 | 206 comments tagged as staff paraphrase (R13) | Flag; themes use customer voice only |
| 10 | Revenue concentrated in Sales | 1 | Basis for D9 (report section 6) | Fix: change the Q3 method |

Full logs: `profiling/data_governance.xlsx` (Issues_Log, Decisions_Log), `outputs/dq_rule_log.csv`, `outputs/exclusions.csv`, `outputs/quality_report.md`.

## B. AI evaluation detail

Source: `outputs/evaluation/evaluation_report.md` (120 hand labels, labelled blind to rating and AI output).

| Measure | Value | 95% CI |
|---|---|---|
| Sentiment accuracy | 96.7% | 91.7-98.7% |
| Sentiment Cohen's kappa | 0.95 | |
| Primary theme accuracy | 85.8% | 78.5-91.0% |
| Theme accuracy, either of the hand-labeller's two themes | 96.7% | |
| Primary theme Cohen's kappa | 0.82 | |
| Theme and sentiment both correct | 83.3% | |

**Per theme** (`outputs/evaluation/per_theme.csv`):

| Theme | Hand-labelled n | Precision | Recall | F1 |
|---|---|---|---|---|
| Staff attitude | 20 | 0.83 | 0.95 | 0.88 |
| Communication and updates | 38 | 0.94 | 0.84 | 0.89 |
| Wait time and turnaround | 27 | 0.79 | 0.85 | 0.82 |
| Price and billing | 14 | 1.00 | 0.86 | 0.92 |
| Work quality and fix | 14 | 0.92 | 0.86 | 0.89 |
| Process and facilities | 7 | 0.56 | 0.71 | 0.63 |
| Vehicle or product, Other | 0 | not measured | | |

- **The 10 example errors** (`outputs/evaluation/errors.csv`):
  - 6 of 10 are the same two themes with primary and secondary swapped, e.g. "clear explanations, long wait".
  - 2 are a different theme choice.
  - 2 are sentiment: one is neutral against positive, and one is mixed against negative.
- **Sentiment confusion** (`outputs/evaluation/sentiment_confusion.csv`): no hand-labelled negative was called positive. One hand-labelled positive was called negative.
- **Vehicle or product and Other** never appeared in the 120-row sample. A blind hand check of AI-labelled comments outside the 150 hand-checked rows is in `labelling/extra_check.xlsx`. It holds 14 Vehicle or product rows, which is every one there is, and 20 of the 84 Other rows (`outputs/derived_numbers.csv`).
  - **Result** (`outputs/evaluation/extra_check_summary.csv`, disagreements with comment text in `outputs/evaluation/extra_check_report.md`):

    | AI theme | n | Primary agrees (precision) | 95% CI | Sentiment agrees |
    |---|---|---|---|---|
    | Vehicle or product | 14 | 6 (43%) | 21-67% | 14 |
    | Other | 20 | 3 (15%) | 5-36% | 16 |

  - **Vehicle or product:** 5 of the 8 misses had the same two themes swapped. Comments explaining the vehicle went to Vehicle in the AI labels and to Communication in the hand labels.
  - **Other:** 13 of the 17 misses were short positive remarks such as "easy peasy" or "smooth sailing". The AI treated these as vague (Other); the hand labels file them under Process and facilities.
  - **Sentiment:** the AI said neutral on 4 short comments that the hand labels call positive.
  - **Impact:** both themes together hold under 1% of dissatisfied comments (`outputs/q1_theme_by_department.csv`).

**Sanity checks on all 5,150 AI labels** (`outputs/sanity/`):

| Check | Result |
|---|---|
| Other as primary theme | 1.6% (flag at 10%) (`theme_distribution.csv`) |
| AI negative or mixed, where the rating is dissatisfied | 99.7% (`sentiment_vs_dissatisfied.csv`) |
| AI negative, where the rating is not dissatisfied | 7.1% |
| AI negative vs dissatisfied share: Service / Parts / Sales | 35.9% vs 33.1% / 26.4% vs 21.3% / 14.8% vs 13.4% |
| Included rows with no comment (no theme) | 24.3% (`label_status.csv`) |

**Voice tag** (`outputs/evaluation/voice_check.csv`, 30 rows):
- Agreement is 86.7% (`outputs/evaluation/evaluation_report.md`).
- Every row tagged as a staff write-up was one.
- 21.1% of hand-labelled staff write-ups were not tagged (`outputs/derived_numbers.csv`).

**Ringwood score vs AI sentiment, D2** (`outputs/evaluation/ringwood_d2.csv`):
- 98.4% of scores 1-4 are AI negative or mixed (`outputs/evaluation/evaluation_report.md`).
- At a score of 6, 15 of 18 are mixed.
- At-risk share is 25.5% at 5 or below of 10 (the headline rule), against 32.1% at 6 or below (`outputs/d2_ringwood_sensitivity.csv`).

## C. Q1 theme shares in full

`outputs/q1_theme_by_department.csv` holds each department by primary and any-mention basis, with and without Essendon and Ipswich. `outputs/q1_theme_by_dealer.csv` and `outputs/q1_theme_by_dealer_department.csv` hold the dealer tables, with `thin` marking n < 30.

## D. Detail cut from the report

Short notes cut from `report.md` to keep it to four printed pages. Each number cites its output file.

- **Noosa.** Noosa's 2.0% dissatisfied share (49 responses) is not comparable with the other dealers: it collects feedback cards at very low volume, 8.5 responses per 1,000 transactions against a median of 26.5, which suggests selective collection (Issues_Log I087 in `profiling/data_governance.xlsx`; share from `outputs/q1_by_dealer.csv`).
- **Service and customer contact.** Service is 9.9% of revenue but has 200,249 jobs against 16,011 vehicles sold, so most customer contact happens there (`outputs/revenue_context.csv`).
- **A second typical comment** (Service, dissatisfied, primary theme Price and billing): "Booked in for $199 special. Left paying $384. Special for who?" (`outputs/theme_example_quotes.csv`).
- **AI use.** Report section 7 gives the short version. The full account is `ai_usage_log.md`: the key prompts and interactions, every case where the AI was wrong and how it was caught, and a dated entry for each labelling step. The extra check on Vehicle or product and Other, and the full evaluation, are in appendix B.
