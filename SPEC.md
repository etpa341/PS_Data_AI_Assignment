# SPEC: Kestrel customer feedback pipeline

## 1. Goal
Turn 52 messy dealer feedback files into one trusted table, label the comments with AI, prove how accurate the labels are, and answer three questions for the Head of Customer Experience:
Q1 What drives negative feedback, by dealer and department?
Q2 How has feedback changed over the year?
Q3 What should be fixed first and what is it worth in dollars?
Window: Oct 2025 to Sep 2026 (matches monthly_revenue.csv).

## 2. Done means
- Every file and sheet is accounted for in the manifest, nothing dropped silently
- Every cleaning decision is in the decision log with evidence
- AI labels are cached, reproducible offline and measured against my hand labels
- Report is 2 to 3 pages with findings, dollar ranges, limits and an honest AI usage log

## 3. Inputs
feedback/ (52 files), reference/dealerships.csv, reference/monthly_revenue.csv, profiling/data_governance.xlsx (Manifest, Issues_Log, Decisions_Log D1 to D5, Data_Requests). Source files are read-only.

## 4. Layers and run order
01_bronze.py: read every file and sheet as-is. Add source_file, source_sheet, source_row. Mapping config per file family in config/file_mappings.yaml (header row, delimiter, columns).
02_silver.py: parse dates per file, normalise ratings, standardise department, map dealer_code, add flags, redact personal data, log every rule. Excluded rows stay in the table with excluded = true and exclude_reason.
03_label.py: classify comments with the LLM (cached).
04_evaluate.py: compare AI labels with my hand labels.
05_gold.py: silver + AI labels + revenue join.
analysis.ipynb: answers Q1 to Q3, charts and sizing, runnable top to bottom.

## 5. Silver schema
feedback_id, source_file, source_sheet, source_row, dealer_code, department, date_raw, feedback_date, date_corrected, month, rating_raw, rating_scale, score_norm (0 to 100), dissatisfied (bool), at_risk (bool), comment_clean (redacted), has_text, voice (customer, staff_paraphrased, unknown), dept_inferred, dq_flags, excluded, exclude_reason.

## 6. Locked decisions (see Decisions_Log)
- D1 Scales: score_norm = (x - min) / (max - min) * 100 using the true scale min and max. Apply the Geelong 2025 inversion fix first. Never average raw ratings across scales. dissatisfied = bottom 40% (1-2 of 5, 1-4 of 10, Tamworth Bad). at_risk = score_norm <= 50 (<=3 of 5, <=5 of 10, Tamworth OK or Bad). Both fixed before any business analysis.
- D2 Ringwood: headline uses the general rule. Report the <=6 of 10 version as a sensitivity row only. Status: to test against AI sentiment.
- D3 Bendigo S = Sales, flagged inferred. Sensitivity run excluding S rows.
- D4 Shepparton: correct 6 rows dated Oct to Dec 2026 back one year. Keep date_raw, set date_corrected.
- D5 Gaps: Toowoomba Q4 2025 (aggregate only, no Sales rows) and Penrith June 2026 (Jun tab is a copy of July, exclude) stay as gaps. Revenue rows are kept so gaps show as missing, not zero.
- D6 Essendon Sales/Service duplicate comments: Service copy kept (12 rows). D7 Ipswich vague dates: month only (10 rows). D8 Hunter -> NSW05, IPS -> QLD03 (580 rows, confirm R5).
- D9 Q3 headline revenue at risk = Service + Parts only; Sales on a separate indicative line (see section 11).
- Also: Chermside FINAL excluded in favour of FINAL v2. Liverpool Q3 dates parsed month/day. Southport Google tab excluded as a different source. Month comes from row dates, not tab names. Penrith, Essendon and Ipswich handled per the Issues_Log and voice column rules.

## 7. Validation rules (each logs rule, rows checked, rows failed, action)
Date parses and falls inside the file period and the window. Rating within the file's scale. Department maps to Sales, Service, Parts or Unknown. Dealer code exists in dealerships.csv. No exact duplicate rows or identical tabs. Rating vs comment sentiment check on every sheet to detect inverted scales. Personal data patterns flagged in comments. Actions are fix, flag, exclude or ask.

## 8. Personal data
Drop customer name, phone, email, rego and customer number columns. Hash IDs only if needed for joins. Redact phone, email and plate patterns in comment text before any API call. Staff names are not needed.

## 9. AI labelling (CONFIRMED)
Themes (one primary, optional second): Staff attitude; Communication and updates; Wait time and turnaround; Price and billing; Work quality and fix; Vehicle or product; Process and facilities; Other. Sentiment: positive, neutral, negative, mixed. Blank comments are tagged no_comment and never sent. Vague comments like "ok" go to Other with sentiment only. If two themes compete, the primary is the theme that best explains the customer's overall verdict. The model is sent the comment text only, never the rating (so labelling matches the blind hand labels and the D2 score-vs-sentiment test is not circular).
Prompt: stored in prompts/classify_v1.txt, JSON-only output with primary_theme, secondary_theme, sentiment, confidence. Validate against a schema and retry once on invalid output.
Model: not assumed; select_model.py lists the models available to the API key and picks the newest Haiku, recorded with its pricing source in config/settings.yaml and ai_usage_log.md; no temperature setting (the current Messages API has none; reruns are reproducible from the cache of raw responses), prompt version and run date written into every output row. The API key is read from the ANTHROPIC_API_KEY environment variable only and never stored in the repo.
Cache: key = hash(redacted text + prompt version + model). Raw responses committed to the repo so the pipeline reruns offline.

## 10. Evaluation
Draw 120 comments, stratified random across dealers and departments (seed 42), customer voice only. Export labelling_sheet.csv with no AI columns. I label theme and sentiment before seeing any model output.
Measure: sentiment accuracy, theme accuracy, per-theme precision and recall, Cohen's kappa, and a table of 10 real errors with reasons. State limits: one labeller, small sample.
Tool: Promptfoo if setup takes under 45 minutes, otherwise a Python comparison script. Use it to compare prompt v1 and v2 on the labelled sample only. Test the Ringwood cut-off (D2) against sentiment.

## 11. Business answers (CONFIRMED)
Q1: dissatisfied share and theme share of dissatisfied comments by dealer and department. Use shares with n, never raw counts. Customer-voice rows only for themes.
Q2: monthly dissatisfied share and mean score with response counts. Show like-for-like dealers and mark gaps. Do not call a trend on thin months.
Q3: priority = frequency x severity x fixability (fixability is a labelled 1 to 3 judgement). Headline revenue at risk = Service + Parts only (recurring revenue): annual revenue (dealer, department) x dissatisfied share x leave rate, split by theme share of dissatisfied comments. Low = dissatisfied at 5%, base = dissatisfied at 10%, high = at_risk at 20%. Sales is reported on a separate line labelled "indicative future repeat and referral sales", never added to the headline: annual sales revenue x dissatisfied share x a repeat-and-referral loss rate of 1% (low), 2.5% (base), at_risk x 5% (high), all labelled assumptions (D9). Leave rates are labelled assumptions with no outcome data behind them. Include a sensitivity table. State that responders are not all customers and that theme ranking does not depend on the leave rate.

## 12. Outputs
data/bronze, data/silver, data/gold, outputs/ (decision log, quality report, evaluation, charts), report.md, ai_usage_log.md, data_dictionary.md, README.md with run order.
