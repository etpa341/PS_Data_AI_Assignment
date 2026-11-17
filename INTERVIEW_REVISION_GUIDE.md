# Interview revision guide: Kestrel Data & AI Challenge

Everything below is taken from the repo (code, report, evaluation, decisions log). Numbers are the ones in the final report.

---

## 0. The 60-second pitch

> Kestrel has 24 dealers sending 52 differently shaped spreadsheets. I built a reproducible Python pipeline (bronze, silver, gold) driven by a per-file YAML config, to produce one cleaned, redacted table of 7,271 rows (7,070 included). I used Claude Haiku 5.5 to label each comment with a theme and sentiment, and measured it against 120 blind hand labels. Then I answered three questions. Service is the problem. The Q2 rise is concentrated in two dealers, and I'm honest that the booking-system link is not proven. About $2.5m a year of Service and Parts revenue is at risk, with the ranking solid and the dollars low-confidence.

---

## 1. Numbers to memorise

### Data and pipeline
| Item | Number |
|---|---|
| Dealers / files / sheets | 24 / 52 / 82 |
| Window | Oct 2025 to Sep 2026 |
| Bronze rows reconciled to profiling manifest | 7,271 = 7,271 (data rows) |
| Excluded rows (kept in table, `excluded=True`, with reason) | 201 |
| Included rows / with a score | 7,070 / 7,060 |
| Issues logged / groups | 161 / 10 |
| Decisions | D1 to D9 (all locked) |
| Validation rules | R01 to R21 plus R10, R11b (`outputs/dq_rule_log.csv`) |
| PII cells dropped at read time | 9,604 |
| Rating scales | 1-5 numeric 6,365 rows; 1-10 (Ringwood) 321; labels 1-5 (Ballarat) 292; stars (Bendigo) 144; Bad/OK/Good (Tamworth) 143 |
| Comments with text (included) | 5,349; customer-voice and labelled 5,150 |
| label_status counts | labelled 5,150; no_comment 1,721; skipped_excluded 201; skipped_voice 199 |

### Key data-quality fixes
- **Geelong 2025:** scale reversed ("1 = Excellent"). 68 rows, fixed with `x -> 6 - x` before normalising.
- **Ringwood:** template change at row 37, 1-5 to 1-10 from Feb 2026. 321 rows. Each block scored on its own scale.
- **Liverpool Q3:** month-first dates, proven by 56 values with a second part over 12.
- **Shepparton:** 6 dates after the 31 Mar closure, moved back one year (D4).
- **Exclusions:**
  - Penrith "Jun 26" is a copy of "Jul 26" (43 rows).
  - Chermside FINAL is a subset of FINAL v2 (112 rows).
  - Essendon cross-tab duplicates (12 rows).
  - 16 other exact duplicates, 4 test rows (Southport), 8 copied Google reviews, and the Toowoomba aggregate summary (6 rows).
- **Gaps (not zeros):** Penrith June 2026, and Toowoomba Oct to Dec 2025.
- **Inferred, awaiting confirmation:** Bendigo "S" as Sales (32 rows, D3); Hunter as NSW05 and Ipswich as QLD03 (580 rows, D8).

### Definitions
- **score_norm** = (x - min) / (max - min) x 100, using the **true** scale min/max, never the observed range.
- **Dissatisfied** = score_norm < 40 (so 1 or 2 out of 5). **At risk** = score_norm <= 50.
- **Like-for-like (Q2):** 21 dealers with rated feedback in all 12 months.

### Q1: where and why
- Dissatisfied share by department: **Service 27.2%** (n=4,836), Parts 16.2% (n=697), Sales 10.1% (n=1,527).
- At risk: Service 38.9%.
- Dissatisfied-comment themes (n=1,436): Communication 28%, Waiting 24%, Price 14%, Work quality 13%, Process 11%, Staff 8%.
- Parts: waiting is 47% (n=105). Sales: staff attitude is 34% (n=140).
- Communication appears in 49% of dissatisfied comments on an any-mention basis.
- Dealers: Parramatta 27.8%, Rockhampton 25.7%, Dandenong 25.4%, Southport 25.2%, Chatswood 24.8%. Highest cells are Service: Parramatta 36.3% (n=311), Dandenong 34.5% (n=319), Chatswood 31.1% (n=180).
- **Noosa 2.0% (n=49)** is not comparable: 8.5 responses per 1,000 transactions against a median of 26.5, which suggests selective collection (I087).
- Dropping Essendon and Ipswich (staff write-ups) moves no share by more than 1.8 points.
- 47 of 66 dealer-by-department theme cells are thin (n<30).

### Q2: what changed
- Dissatisfied share **18.9% to 24.4% (+5.5 pts)**, Oct to Dec 2025 against Jul to Sep 2026.
- Dealer-clustered bootstrap (5,000 draws, seed 42) interval: **+1.0 to +10.6**. Leave-one-dealer-out minimum: +3.6.
- By department: Service +6.8, Sales +5.5, Parts -5.9. Only 10 of 21 dealers rose.
- **Parramatta (14.2% to 44.0%) and Dandenong (17.2% to 33.3%)** account for +3.3 of the +5.5.
- Without both, the rise is **+2.4 (interval -0.5 to +5.7), not significant**.
- Dandenong's May tab banner: "new online booking system went live 5 May ... log everything!"
- Booking mentions in dissatisfied comments:
  - Parramatta 8.2% to 20.2%.
  - Dandenong 2.3% to 17.7%.
  - Other dealers about 3%.
- **Counter-evidence I disclose:** April was already high (26.8% group-wide), and the Process label did not rise at Parramatta (33% to 32%). Dandenong's jump is partly "log everything" (more logging). Parramatta looks like a real service problem, since satisfied responses fell and volume was flat.

### Q3: what it is worth
- Headline revenue at risk (Service + Parts), base case: **$2.47m a year (low $1.23m, high $7.17m)**.
- Sales is a separate indicative line: low $0.76m, base $1.91m, high $6.15m.
- Formula: annual revenue (dealer, department) x dissatisfied share x leave rate. The high case uses the at-risk share instead.
- Leave rates: Service + Parts 5% / 10% / 20%. Sales 1% / 2.5% / 5%. All are my **assumptions**, with no churn data.
- Why Sales is out of the headline (D9): a naive method gave $10.11m with Sales at 76%. Sales is 88.7% of the $839m revenue but has the lowest dissatisfied share, and a car already sold is not recurring revenue.
- Priority = frequency x severity x fixability:
  1. Communication $0.71m, 28.6%, fixability 3.
  2. Waiting $0.65m.
  3. Work quality $0.34m (severity 59%).
  4. Price $0.33m.
  5. Process $0.28m.
  6. Staff $0.14m.
- The top three are the same without fixability. The ranking is robust to the leave rate.
- Biggest dealers by base revenue at risk: Parramatta $195k, Dandenong $185k, Chermside $163k.

### AI labelling
- Model: **Claude Haiku 5.5** (`claude-haiku-5-5`), picked by `select_model.py` as the newest Haiku available to the key. Prompt v1 was never edited after evaluation.
- Full run: **5,090 API calls, 0 failures, $1.23** (10.84m input and 0.30m output tokens at $0.10 / $0.50 per million).
- Eight closed themes plus sentiment (positive, neutral, negative, mixed), with JSON output and a confidence value.
- Evaluated on **120 blind hand labels** (rating hidden):
  - Sentiment accuracy **96.7%** (CI 91.7 to 98.7), kappa 0.95.
  - Primary theme **85.8%** (CI 78.5 to 91.0), kappa 0.82.
  - Lenient theme accuracy (either human theme) 96.7%.
  - Both correct 83.3%.
- Weak spot: **Process and facilities** has precision 0.56 (n=7), and the booking finding leans on it. That's why I used keyword evidence alongside it.
- Vehicle or product and Other were not in my sample. I did an extra blind check of 14 and 20 comments: the AI's theme was right for 6 and 3 (precision only). Both are under 1% of dissatisfied comments.
- Voice tag (staff write-up vs customer) on 30 rows: agreement 86.7%, precision 100%, recall 78.9%.
- Ringwood D2 test: 62 of 63 scores of 1 to 4 are AI negative or mixed. A 6 out of 10 is mostly mixed (15 of 18). At risk is 25.5% at 5 or below against 32.1% at 6 or below. I kept the common rule and show 6 or below as a sensitivity, so Ringwood's at-risk share may be understated.

### Redaction bug (my best "where AI was wrong" story)
- Staff-name redaction was **case-sensitive**, and the check used the same pattern, so it agreed with itself.
- **152 of 5,349 comments** (23 dealers) reached the model with a staff first name.
- Fix: case-insensitive match plus an **independent token-by-token checker with no shared code** (`staff_name_tokens_left`). After the fix, 0 left. I relabelled the 152 comments (22 labels changed, **$0.037**).
- Unlisted staff names (4) are kept only as sha256[:16] hashes in `config/redaction.yaml`.

### Other places the AI was wrong (from `ai_usage_log.md`)
- Said `claude-haiku-5-5` did not exist and swapped in 4.5 from training knowledge. The pricing page showed it did.
- Reported 163, then 76, colliding record IDs. An independent pandas check showed 0.
- Matched Springwood to Ringwood (substring match); fixed with a longest-match rule.
- The first staff-paraphrase regex tagged first-person comments as staff write-ups.
- The first dollar method let car sales dominate.
- Opening a CSV in Excel re-saved it with different date formats; caught because issue counts changed.

---

## 2. Architecture in one picture

```
feedback/ (52 raw files, gitignored)
   │  01_bronze.py  + config/file_mappings.yaml
   ▼
BRONZE  data/bronze/bronze_rows.csv   every non-blank row as text, classed header/banner/data/total/note; PII dropped
   │  02_silver.py  (no LLM, no network)
   ▼
SILVER  data/silver/feedback_silver.csv   dealer, date, department, score_norm, redacted comment, voice, exclusions
   │  03_label.py   (Claude Haiku, cached)
   ▼
labels.csv + cache.jsonl
   │  04_evaluate.py  (vs 120 blind hand labels)       05_gold.py (silver + labels + revenue)
   ▼
GOLD    feedback_gold.csv (7,271 rows)   dealer_month_dept.csv (24 x 12 x 3 panel)
   ▼
analysis.ipynb  → Q1, Q2, Q3 → report.md / PDF
```

**Why medallion?** Bronze is raw, so I can always prove nothing was lost (reconciled to the manifest). Silver holds all the cleaning decisions, each logged. Gold adds the AI labels and revenue.

**Why stack, not join?** The files are different slices of the same thing. The only join is monthly revenue on dealer and month, kept as a separate panel so revenue isn't repeated on every feedback row.

**Why Python and YAML, not SQL?** Every file needs its own rules. A per-file mapping config is easier to read and test.

---

## 3. Key functions to be able to explain

### `01_bronze.py`
- **`family_for(fname)`**: matches a filename to exactly one YAML family via `fnmatch`. It raises an error if it matches 0 or more than 1.
- **`sheet_config(fam, fname, sheet)`**: layers the config. Defaults, then family, then sheet, then sheets_by_file. This is how Ringwood's per-file header rows work.
- **`read_csv`**: decodes strictly (`bytes.decode(enc)`), so a wrong encoding fails loudly. This matters for Wollongong's cp1252.
- **`read_xlsx`**: opens with `data_only=True, read_only=True`, so source files are never modified.
- **`bronze_sheet(...)`** is the core:
  - Classes every row as banner, header, data, total or note.
  - **Fails loudly** if a header cell isn't in the config, or data sits in an unnamed column.
  - Supports **multiple header rows** per sheet (Frankston, Ringwood template changes).
  - Handles `drop:` targets: counts PII cells, never writes them, and collects staff names for later redaction.
  - Stores a one-way `raw_row_hash` (sha256[:16]) so exact duplicates can be found without keeping PII.
- **`main()`**: reconciles to the profiling manifest and runs PASS/FAIL checks, including "no PII column names in output" and "bronze data rows total == manifest total". It exits non-zero on failure.

### `02_silver.py`
- **`parse_date(s, fmt)`**: per-file format (excel serial, dmy, mdy, d_mon_yy, iso). Excel serial = 1899-12-30 + days. ISO text is accepted for every format, because Excel datetime cells arrive as ISO.
- **`vague_month(s)`**: "early Oct" or "Aug?" gives a month only, and the date stays empty (D7).
- **`period_months(fname, sheet)`**: infers the period from the tab or file name, used for the "row month inside period" check (R06).
- **`rating_value(raw, scale)`**: handles numeric, label and star scales and returns `(value, reason)`. Out-of-scale and unparseable values get a reason and no score. Nothing is guessed.
- **Normalisation** (around line 349): flip inverted sheets first, then `(x-lo)/(hi-lo)*100`, then `dissatisfied = score_norm < 40` and `at_risk = <= 50`.
- **`redact(text)`**: regexes for email, AU phone, rego (word-anchored and plate pattern), and "Firstname Lastname - " prefixes.
- **`redact_staff(text, staff_re)`**: replaces listed names (any case) and unlisted names by hash.
- **`staff_name_tokens_left`** and **`pii_left`**: independent verification that shares no code with the redactors. **This is the verifier-independence lesson.**
- **Voice tagging**: `PARAPHRASE_RE`, `FIRST_PERSON_RE` and `STAFF_CUE_RE` separate staff third-person write-ups ("Cust said...") from customer words. Themes use customer voice only.
- **Exclusions:**
  - Whole sheets from config, each **re-checked against the data** (`subset_of`, `identical_to`, `header_contains`, `kind`). The run fails if the evidence stops holding.
  - Test rows, exact duplicates (`raw_row_hash`), Essendon cross-tab copies, and dates outside the window.
  - Excluded rows stay with a reason.
- **Rule R10 (rating vs comment sentiment)**: pools by family + scale, and positive-word comments must not score lower than negative-word ones. It detects suspected inversion, and Geelong 2025 failed before the fix and passes after.
- **`log(rule_id, rule, checked, failed, action)`**: every validation rule records rows checked, rows failed and the action taken.

### `03_label.py`
- **`parse_and_validate(text)`**: strict schema check. Exactly 4 keys, theme in the closed list, secondary different from primary, sentiment in the list, confidence between 0 and 1. Tolerates a code fence and nothing else.
- **`cache_key(text, prompt_version, model)`**: sha256 of text, version and model. Raw responses are stored in `cache.jsonl`, so reruns are offline and identical.
- **Prompt-drift guard**: if the prompt text changes but the version doesn't, the run stops. This keeps the cache valid.
- **`label_one`**: one retry on invalid output, then `failed_validation`. Raw responses are kept.
- **Concurrency**: `ThreadPoolExecutor`. Only the main thread writes the cache, one line flushed per result, so an interrupted run resumes.
- **Modes**: `--offline` (default), `--live`, `--dry-run` (FakeClient, separate directory), `--estimate`.
- **Every silver row gets exactly one output row with a `label_status`**, and an assert checks this, so nothing is dropped silently.
- **Privacy:** the key is read from the environment or a gitignored `.env`, never the repo. The model sees redacted comment text only, never the rating, so its labels can be tested against ratings.

### `04_evaluate.py`
- **`cohen_kappa`**: (po - pe)/(1 - pe), agreement beyond chance.
- **`wilson(k, n)`**: Wilson score interval, better than the normal approximation for proportions near 0 or 1 and small n.
- **`per_class`** gives precision, recall and F1. **`confusion`** is a crosstab.
- **`ringwood_d2`** is the 1-10 score against AI sentiment test.

### `05_gold.py`
- Joins silver and labels, and builds the dealer x month x department panel (24 x 12 x 3) from `monthly_revenue.csv`.
- **Gaps are NaN with a `gap_reason`, not zero.** A dealer-month with no feedback gets empty metrics. A department with no rows in a dealer-month that does have feedback gets `responses = 0`.

### `analysis.ipynb`
- **`cluster_bootstrap(t, reps=5000, seed=42)`** resamples **dealers** with replacement and recomputes the pooled change. The naive CI treats 3,000+ responses as independent when they cluster in 21 dealers.
- **`pooled_change`**, plus **per-dealer contribution** (contributions sum to the pooled change) and **change without each dealer**.
- **`summarise`** gives n, dissatisfied share and a Wilson CI. The `THIN = 30` flag marks cells that are not ranked.
- **Q3 `theme_split`**: splits each cell's revenue at risk by that cell's dissatisfied theme mix. If the cell has fewer than 30 comments it falls back to the department mix.

### `config/file_mappings.yaml` (recap of bronze)
- `defaults`, then `families` (files pattern, format, delimiter, encoding, header_rows, sheets, columns with `drop:` targets).
- Silver-only keys: `scales`, `department_map`, `site_aliases`, `date_format`, `rating_scale`, `invert_sheets`, `exclusions`.
- Quirks encoded in config, not code: Chatswood `;` delimiter, Wollongong cp1252, Frankston header rows `[1, 160]`, Liverpool `date_format_by_file`, Geelong `invert_sheets: ["2025"]`.

### Tests
`tests/test_pipeline.py` has 11 pytest tests using a fake client and dummy data, with no API calls. They cover the schema, one retry, cache hits, prompt-drift stop, metrics on dummy data, and gaps being missing rather than zero.

---

## 4. Decisions and trade-offs (expect "why did you...?")

| Decision | Why | Trade-off / risk |
|---|---|---|
| **D1: normalise to 0-100, share dissatisfied** | Scales differ (1-5, 1-10, 3 labels, stars). A share below a threshold is robust to scale length and easy to explain. | Midpoint of 3/5 leans negative. Tamworth has only 3 levels, so its shares are coarse. |
| **D2: Ringwood stays on the common rule** | Comparability across dealers. 6 or below shown as a sensitivity row. | Ringwood's at-risk share is likely understated. |
| **D3: Bendigo S = Sales** | Only other code besides SV and P. Hand review: 8 of 19 clearly Sales, 0 clearly Service. | One reviewer. 32 rows. Sensitivity run without them. |
| **D4: Shepparton future dates moved back 1 year** | Row order puts them among rows dated exactly one year earlier. | Inference. Low stakes (6 rows). |
| **D5: gaps stay gaps** | Zero would bias trends. | Toowoomba trend starts in January. |
| **D6: Essendon duplicates, keep Service** | 0 of 12 contain sales keywords, 2 contain service keywords. | Weak evidence, so it is a hand judgement. At most 12 rows. |
| **D7: Ipswich vague dates, month only** | Month word is in the row; each month occurs once in the window, so the year is unambiguous. | 10 of 277 rows. "Aug?" may be off by one month. |
| **D8: Hunter and IPS alias mappings** | No other dealer fits. Brand mix matches. | 580 rows depend on it. Needs head-office confirmation (R5). |
| **D9: Sales out of the headline** | Sold car is not recurring revenue. Naive method put 76% of the total on Sales. | Might understate the value if unhappy buyers also stop servicing. |
| **LLM, not keyword rules or topic models** | Comments are free text with sarcasm and mixed sentiment. A closed theme list makes results countable. | Needs evaluation. One labeller, n=120. |
| **Haiku 5.5** | Cheap ($1.23 for the full run), fast, re-runnable. | Smaller model. Theme accuracy 85.8%. |
| **Model sees text only, not the rating** | Lets me test labels against ratings, an independent signal. | Loses context a human would use. |
| **Closed 8 themes + secondary** | Countable, evaluable, comparable. | Forces fit. "Other" and "Vehicle" are rare. |
| **Cache of raw responses** | Offline rerun, identical results, no API key needed. | Cache must be invalidated on any prompt change (version and sha guard). |
| **Fail loudly in bronze** | Unknown header or orphan column stops the file. | More config work, but no silent loss. |
| **Config-driven, not code per dealer** | Auditable quirks, issue IDs in comments. | Config grows. 25 families. |

---

## 5. Likely interview questions, with talking points

**"Walk us through the pipeline."** Use the diagram in section 2. Stress reconciliation (7,271 = 7,271), the rule log, and that excluded rows stay in the table.

**"How do you know the AI output is right?"** 120 blind hand labels with the rating hidden. I wrote the definitions and the prompt came from them, so the AI is judged by the same rules. I report accuracy with Wilson CIs and kappa, then sanity checks (AI sentiment against rating-based dissatisfaction, Ringwood test), plus the extra check for classes the sample missed. Limits: one labeller, small n, no Noosa rows.

**"Why not let the AI label the sample?"** It would measure the AI against itself.

**"What's the weakest part?"** Process and facilities (precision 0.56), and the booking finding uses it. I triangulated with keyword search. Also the dollar figures, which are built on assumed leave rates, with no churn data.

**"Is the Q2 rise real?"** Yes at group level (clustered CI +1.0 to +10.6, and every leave-one-out is at least +3.6). But it's concentrated: without Parramatta and Dandenong it's +2.4 and not significant. The booking-system link fits the timing but isn't proven. April was already high, and Dandenong's banner says "log everything", so some of the jump is more logging.

**"Why a clustered bootstrap?"** Responses cluster within dealers with different collection habits, so treating 3,000+ responses as independent gives a falsely narrow interval. Resampling whole dealers respects that.

**"Why Wilson, not the normal interval?"** It behaves better for small n and proportions near 0 or 1, and many cells are thin.

**"Tell us about a bug the AI introduced."** The redaction story. The check reused the redaction's own pattern, so it agreed with itself and missed 152 comments. Lesson: a verifier must be independent of the thing it verifies. I wrote a token-by-token check with no shared code.

**"What about privacy?"** `drop:` columns never leave bronze, and only counts and a one-way hash are kept. Comments are redacted before any model call. The raw `feedback/` and `data/bronze/` are gitignored. Staff names not in any column are kept only as hashes. Redaction is best effort, and I say so.

**"What would you do differently or improve?"**
- Prompt v2 with explicit rules for "explaining how a vehicle works" and short "easy" comments, validated on a fresh sample.
- A second labeller, to measure inter-rater agreement. Add Noosa to the sample.
- Get the missing data: Penrith June, Toowoomba raw Q4 data, confirmation of Bendigo "S" and the Hunter and IPS codes.
- Ask Parramatta and Dandenong for the go-live dates and how logging changed.
- Replace assumed leave rates with real churn or repurchase data.
- Add a CI check or `pytest` coverage for silver rules, not just the label pipeline.
- Consider structured outputs or tool use for the JSON instead of validate-and-retry.
- Cost and scale: batch API (the config already holds batch prices), and incremental loads for monthly files.

**"What was new or challenging?"** (pick your own, but candidates)
- Treating the AI as untrusted: spec before code, independent checks, and logging every place it was wrong.
- Making cluster-aware statistics part of the answer, and being honest when the headline weakens (+5.5 down to +2.4).
- The messy-file long tail: banners, template changes mid-sheet, reversed scales, M/D dates.
- Deciding what not to claim (Noosa, Sales dollars, booking causality).

**"How would this scale / productionise?"** Landing zone for files, a schema-per-family registry (the YAML), validation as gating rules, label cache keyed by text, prompt and model, a monitored labelling job with drift checks, and a gold table in a warehouse. Move from batch folders to a standard submission template, which is the real fix.

**"Why Sales out of the headline?"** See D9: the $10.11m naive figure was 76% Sales. A car already sold isn't recurring revenue, so I show Sales on its own indicative line.

**"Cost?"** Full run $1.23 (5,090 calls). Relabel $0.037. A max_tokens of 2,000 covers default thinking plus about 40 tokens of JSON. 200 truncated 1 in 36.

---

## 6. Caveats you should volunteer before they ask
- One labeller, 120 rows, no Noosa. Theme precision for Process (7 rows), Vehicle and Other is weak.
- Leave rates and fixability are my judgement.
- 29 of 48 headline cells use the department theme mix because the dealer cell is thin.
- Responders aren't all customers. Collection differs by dealer (cards, surveys, staff logs). Essendon and Ipswich are staff write-ups.
- Staff-name redaction is best effort, and 152 comments reached the model before the fix.
- Hunter and IPS mappings and Bendigo "S" are inferred and still need confirming.

---

## 7. Where to look in the repo (quick map)
- Report: `deliverables/report.md` / `.pdf`. Appendix: `deliverables/appendix.md`.
- Governance workbook (decisions, issues, manifest): `deliverables/data_governance.xlsx`. Sheets: Manifest, File_Profile, Column_Dictionary, Scales_and_Labels, Issues_Log, Dealer_Coverage, Decisions_Log, Verification_Plan, Data_Requests, QA_Checks.
- Rule log: `outputs/dq_rule_log.csv`. Quality report: `deliverables/quality_report.md`.
- Evaluation: `deliverables/evaluation/evaluation_report.md`. AI usage: `deliverables/ai_usage_log.md`.
- Prompt: `deliverables/classify_v1.txt`. Config: `config/*.yaml`. Spec: `SPEC.md`.
