# Profiling (step 1: understand the files, no cleaning)

`profile.py` reads every file and every sheet in `../feedback/` (read-only) plus `../reference/`, and writes `data_governance.xlsx`. It makes no changes to the source files, does no cleaning or merging, and makes no LLM or network calls.

## Rerun

```bash
pip install pandas openpyxl        # tested with Python 3.13, pandas 2.3, openpyxl 3.1
python profiling/profile.py         # from the repo root
```

On Windows terminals, set `PYTHONIOENCODING=utf-8` if the console complains about characters. The script exits non-zero if any QA check fails.

Close the source workbooks in Excel before running. An open workbook leaves a `~$...xlsx` lock file in `feedback/`. The script lists it in the Manifest as "not data" and skips it.

## Output tabs (`data_governance.xlsx`)

| Tab | Contents |
|---|---|
| Manifest | One row per file and sheet: dealer_code and match evidence, period covered (parsed min/max), period implied by the name, data row count, sheet kind, notes / needs-decision |
| File_Profile | One row per file and sheet: header rows, columns, banners, totals, repeated headers, template changes, encoding/delimiter, date formats and order, rating scale and values, inversion heuristic, department values, comment stats, PII counts (counts only), duplicates |
| Column_Dictionary | Every raw column in every template: plain-English meaning, proposed standard field, PII flag |
| Scales_and_Labels | Rating scales with the files that use each; every raw department value mapped to Sales/Service/Parts/Unknown, with comment-keyword evidence; vehicle-brand check per dealer against `dealerships.csv` |
| Issues_Log | id, file, sheet, issue, evidence (rows or counts), severity, proposed action (fix / flag / exclude / ask), status |
| Dealer_Coverage | Dealer × month row counts, months with zero rows, revenue months, and revenue after closure |
| Decisions_Log | Locked or to-test decisions (D1 to D9): rationale, evidence (recomputed from the data on each run), files, implementation, risk, linked Issues_Log ids. Ids are resolved by rule on each run, because issue ids are renumbered |
| Verification_Plan | Checks to run once AI sentiment labels exist (V1 Ringwood sensitivity, V2 definition check, V3 Bendigo S) |
| Data_Requests | Questions and data requests to dealers and head office (R1 to R5), each linked to a decision |
| QA_Checks | Self-checks: all files present, totals reconcile, all dealers covered, every issue has evidence |

## How it works (so the results can be checked)

- **Header detection.** A row counts as a header if it has at least 2 cells that map to known column roles, including at least one core field. Every cell must be a short text label, not a date or a number. A header row found further down the sheet starts a new block, which is how template changes are detected. A header-like row directly above another one is treated as a banner (for example the merged group header in Ballarat).
- **Row classes.** Rows are classed as data, blank, total/summary (`Total ...`, `Grand Total`), or footer note (a single long text cell with no date). Rows above the header are banner rows.
- **Dates.** Each value is classified by format. Day/month order is decided per sheet from the evidence: if any first part is > 12 the order is D/M, and if any second part is > 12 it is M/D. If neither occurs, the order is "unproven". Dates are then compared with the period in the file or tab name and with the Oct 2025 to Sep 2026 window. A "suspected year typo" is an out-of-window date that fits its neighbours once it is shifted back one year.
- **Rating inversion.** This is a heuristic, so results are only ever "suspected". It compares the mean rating of comments with positive keywords against comments with negative keywords. It needs at least 8 of each and a gap of at least 0.5 to report a direction.
- **PII.** Name, phone, email, rego and customer-number columns are counted. Free text is scanned with regex for phone, email and "rego XXXX" patterns, and for a "Firstname Lastname - " prefix. Only counts are written. No PII values appear in the workbook. The banner and footer text that is written contains staff names at most.
- **Duplicates.** Checked as exact duplicate rows within a sheet, identical sheets (content hash), and overlapping (date, rating, comment) keys between sheets of the same dealer. It also checks for the same date and comment in more than one tab, comment text reused across dealers, and record-ID collisions across dealers, compared pairwise on content.

## Known limitations

- Keyword lists for the inversion check and department evidence are small and hand-written. Use them as signals only.
- Dealer matching uses suburb names in file names plus a short alias table. The two aliases, `Hunter` → NSW05 and `IPS` → QLD03, are judgement calls and are flagged as needing a decision.
- "Staff paraphrase" only catches comments that start with *Cust / Customer / Said*. It undercounts.
