# The Kestrel project: the complete story

Problem, discovery, build, findings, money, recommendations, and what I'd do next. Numbers come from the final report, the decisions log and the evaluation outputs.

---

## Chapter 1. The problem

**Kestrel Motor Group** has 24 dealerships across Victoria, NSW and Queensland, selling and servicing several brands. Each dealer collects customer feedback from Sales, Service and Parts customers and sends it to head office. Nobody ever agreed on a template. Each spreadsheet grew organically, built by whoever owned it at the time.

The Head of Customer Experience couldn't answer simple questions:
1. **Where is negative feedback concentrated, and why?**
2. **Has anything changed over the year?**
3. **Where should Kestrel focus first, and what is it worth?**

The brief had four tasks: bring the data together, decide what you can trust, use AI to make sense of the words, and answer the business. It also asked for honesty about how AI was used.

---

## Chapter 2. What the data looked like

52 files (.xlsx and .csv), 82 sheets, 7,271 rows, Oct 2025 to Sep 2026. Treat everything with suspicion.

**Every file was different.** I profiled all of them first and logged **161 issues in 10 groups**. The ones that would have silently corrupted results:

| Problem | Example | Why it matters |
|---|---|---|
| **Different rating scales** | 1-5 numbers; Ringwood's 1-10; Ballarat's "Very satisfied" labels; Bendigo's ★ stars; Tamworth's Bad/OK/Good | You can't average a 4 out of 5 with a 7 out of 10. |
| **A reversed scale** | Geelong's 2025 tab says "1 = Excellent, 5 = Poor" (68 rows) | Happy customers would count as unhappy. |
| **A template change mid-sheet** | Ringwood switches from 1-5 to 1-10 at row 37 (321 rows); Frankston changes at row 160 | One column, two meanings. |
| **Date formats** | Excel serial numbers, d-Mon-yy, ISO, day-first and month-first (Liverpool Q3 is US-style) | Wrong months, wrong trends. |
| **Layout noise** | Banner rows above headers, total rows, footers, empty sheets, `;` delimiters, cp1252 encoding | Rows lost or misread. |
| **Duplicates and copies** | Penrith "Jun 26" tab is a copy of "Jul 26"; Chermside FINAL sits inside FINAL v2; Essendon logs the same comment in two tabs | Double-counting. |
| **Gaps** | Penrith June 2026 missing; Toowoomba Oct–Dec 2025 only a summary of counts | Zero would bias trends. |
| **Ambiguous identity** | "Hunter" and "IPS" files with no suburb name; Bendigo's department code "S" | Which dealer? Which department? |
| **Personal data** | Names, phones, emails, number plates, customer IDs, staff names, in columns and inside comments | Must be handled as if real. |
| **Staff write-ups** | At Essendon and Ipswich staff wrote the comment ("Cust said...") | Not the customer's own voice. |

---

## Chapter 3. How I decided to build it

**Principle: spec before code.** I wrote a spec (`SPEC.md`) fixing the layers, the score scale, the eight themes and the dollar method before any pipeline code existed. I used Claude Code to write the pipeline to my spec, and a separate Claude chat as reviewer and report drafter. I made the decisions.

**Architecture (medallion layers):**

```
feedback/ → BRONZE (every row as read) → SILVER (cleaned, redacted, validated)
          → AI labels (themes + sentiment) → GOLD (silver + labels + revenue) → analysis → report
```

- **Bronze (`01_bronze.py` plus `config/file_mappings.yaml`)** reads every file as-is. A YAML "recipe book" says, per dealer, how to open the file, where the headers are, and how to rename each column to a standard name. Personal columns marked `drop:` are never written. If anything is unexpected (an unknown header, data in an unnamed column) it **stops loudly**. It then reconciles its row count to my profiling manifest (7,271 = 7,271).
- **Silver (`02_silver.py`)** holds all the cleaning decisions, each logged with rows checked, rows failed and action taken. No LLM and no network here.
- **Labelling (`03_label.py`)** uses Claude Haiku 5.5 and caches every response, so reruns are offline and identical.
- **Evaluation (`04_evaluate.py`)** tests the AI against my hand labels.
- **Gold (`05_gold.py`)** joins everything and adds monthly revenue.
- **`analysis.ipynb`** answers Q1 to Q3.

**Why one stacked table, not joins?** The files are different slices of the same thing, so I stack them. The only join is monthly revenue on dealer and month, kept as a separate dealer x month x department table so revenue isn't repeated on every feedback row.

**Why Python and YAML, not SQL?** Every file needs its own rules. A per-file config is easier to read, audit and test.

---

## Chapter 4. How the data was cleaned (decisions D1 to D9)

Every judgement call was logged, with evidence, in the Decisions_Log (`data_governance.xlsx`).

**D1. One common score.** Every rating is rescaled to 0 to 100: `(x - min) / (max - min) x 100`, using the *true* scale min and max. Tamworth's Bad/OK/Good becomes 0/50/100, stars are counted, labels are mapped, and Geelong 2025 is flipped (`6 - x`) before scaling.
- **Dissatisfied** = below 40 (so 1 or 2 out of 5).
- **At risk** = 50 or below.
- A share below a threshold is robust to scale length and easy to explain.

**D2. Ringwood's 10-point scale.** I kept it on the same rule as everyone else for comparability and show "6 or below" as a sensitivity only. A test against AI sentiment backed this up: 62 of 63 scores of 1 to 4 were AI negative or mixed. The cost is that Ringwood's at-risk share may be understated (25.5% at 5 or below, 32.1% at 6 or below).

**D3. Bendigo "S" = Sales** (inferred, 32 rows). A hand review found 8 of 19 clearly Sales and none clearly Service. A data request to confirm it is raised.

**D4. Shepparton** has 6 dates after the 31 March closure. They sit in file order among rows dated exactly one year earlier, so they were moved back one year and flagged.

**D5. Gaps stay gaps.** Penrith June 2026 and Toowoomba Q4 2025 are reported as missing (NaN with a reason), never as zero.

**D6. Essendon duplicates.** Where the same comment, date and score appear in both the Sales and Service tabs, keep Service (12 rows). Hand review showed they describe workshop visits.

**D7. Ipswich vague dates.** "Early Oct" or "Aug?" gives the month only; the exact date stays empty.

**D8. Hunter and IPS** are mapped to NSW05 and QLD03 by alias, because brand mix fits and no other dealer does (580 rows, flagged, awaiting head-office confirmation).

**D9. Revenue method** (see Chapter 8).

**Exclusions** (201 rows, all kept in the table with `excluded = True` and a reason): the copied Penrith tab (43), the superseded Chermside file (112), copied Google reviews (8), the Toowoomba summary (6), exact duplicates (16), Essendon cross-tab copies (12) and test rows such as "TEST" and "asdf" (4). Each whole-sheet exclusion is re-checked against the data every run, and the run **fails** if the evidence stops holding.

**Validation rules (R01 to R21)** each report what passed, what failed and what was done. Examples:
- Rating within the true scale (R07).
- Day/month order proven per file (R03).
- Rating-vs-comment sanity (R10): positive-word comments must not score lower than negative-word ones. This is what catches a reversed scale, and Geelong failed before the fix and passes after.

**Privacy.**
- Name, phone, email, plate and customer-ID columns were dropped at read time (9,604 cells). Only a count and a one-way row hash survive.
- Phone, email, plate and "Firstname Lastname - " patterns in the comment text are redacted.
- Staff first names become `[STAFF]`.

---

## Chapter 5. Making sense of the words (the AI)

**What the model does.** For each customer comment, Claude Haiku 5.5 returns strict JSON: a **primary theme**, an optional **secondary theme**, a **sentiment** and a **confidence** (0 to 1).

**The eight themes:**
1. Staff attitude
2. Communication and updates
3. Wait time and turnaround
4. Price and billing
5. Work quality and fix
6. Vehicle or product
7. Process and facilities
8. Other (vague, e.g. "ok")

**The four sentiments:** positive, neutral, negative, mixed (mixed needs at least one real positive and one real negative).

**Design choices:**
- **A closed list of themes**, so results can be counted and checked.
- **The model sees only the redacted text, never the rating.** That lets me test its labels against the ratings as an independent signal.
- **Only customer-voice comments are labelled** (5,150). Staff write-ups are skipped (199), as are empty comments (1,721) and excluded rows (201).
- **Tie-break rules in the prompt** settle the common overlaps. For example, booking problems go to Process, back-ordered parts go to Wait time with Communication as secondary, and the "credit rule" assigns the theme the customer credits.
- **Strict validation with one retry**, and every raw response is cached. Cost: **$1.23** for 5,090 calls, with 0 failures.

**How I know it works:**
- I labelled **120 comments blind** (rating hidden) and wrote the theme definitions. The prompt was built from my definitions, so the AI is judged by the same rules. Letting the AI label the sample would have measured it against itself.
- **Sentiment 96.7% accurate** (95% CI 91.7 to 98.7, kappa 0.95).
- **Primary theme 85.8%** (CI 78.5 to 91.0, kappa 0.82), or **96.7%** if either of my two themes counts. Most misses swap two themes on a comment about two things.
- **Weak spot:** Process and facilities has precision 0.56 (7 labelled rows). Vehicle or product and Other were not in my sample, so I checked 14 and 20 of the AI's labels: it was right for 6 and 3 (precision only). Both are under 1% of dissatisfied comments.
- Voice tag (staff write-up vs customer): 86.7% agreement on 30 rows.

---

## Chapter 6. What I found, Q1: where and why

**Service is the problem.**

| Department | Responses | Dissatisfied |
|---|---|---|
| Service | 4,836 | **27.2%** (38.9% at risk) |
| Parts | 697 | 16.2% |
| Sales | 1,527 | 10.1% |

**Why (themes in dissatisfied comments, n=1,436):** Communication 28%, Waiting 24%, Price 14%, Work quality 13%, Process 11%, Staff 8%. Counting any mention, communication appears in **49%** of dissatisfied comments. A typical one: *"left a voicemail, sent a text, and emailed. triple silence."*

**It varies by department:**
- **Parts:** waiting is 47% (usually back-orders).
- **Sales:** staff attitude is 34% (n=140).
- **Service:** communication 29%, waiting 25%.

**By dealer**, the differences are modest. Most are 20 to 25% dissatisfied. The highest cells are all Service: Parramatta 36.3%, Dandenong 34.5% and Chatswood 31.1%. Noosa's 2.0% (49 responses) isn't comparable: it collects feedback cards at a very low rate (8.5 responses per 1,000 transactions against a median of 26.5), which suggests selective collection.

**Caveat:** 47 of 66 dealer-by-department theme cells have fewer than 30 comments, so dealer-level theme claims are indicative. Dropping the two staff-write-up dealers moves no share by more than 1.8 points.

---

## Chapter 7. What I found, Q2: what changed over the year

Dissatisfaction rose from **18.9% to 24.4%** (+5.5 points), Oct–Dec 2025 against Jul–Sep 2026, using the 21 dealers with feedback in all 12 months.

**Is it real?** A naive test treats 3,000+ responses as independent, which they aren't, since they cluster in dealers with different collection habits. So I resampled whole dealers (5,000 draws) and dropped dealers one at a time. The rise survives (interval +1.0 to +10.6; minimum +3.6 when dropping any one dealer), though the low end is near zero.

**But it's concentrated.** Only 10 of 21 dealers rose. **Parramatta (14.2% to 44.0%) and Dandenong (17.2% to 33.3%)** account for +3.3 of the +5.5 points. Without both, the rise is **+2.4 (interval -0.5 to +5.7), not significant**. The other 19 dealers settled at about 20 to 25%.

**The likely cause is the booking system.** Both jumped in May 2026. Dandenong's May tab says "new online booking system went live 5 May. Expect some teething issues - log everything!" Booking mentions in dissatisfied comments rose from 8.2% to 20.2% at Parramatta and from 2.3% to 17.7% at Dandenong, against about 3% elsewhere.

**What's not proven:**
- Dissatisfaction was already high in April.
- The Process and facilities label didn't rise at Parramatta (33% to 32%).
- Dandenong's "log everything" suggests part of its jump is more logging, not worse service.
- Parramatta looks like a real problem: satisfied responses fell, volume was flat, and communication complaints (33% to 44%) and waiting complaints (31% to 41%) rose.

The timing fits a booking-system effect but does not prove one.

---

## Chapter 8. What I found, Q3: what it's worth

**The question:** where to focus first, and roughly how many dollars are at stake?

**The calculation (D9):**

```
Revenue at risk = annual revenue (dealer x department)
                  x share of customers dissatisfied
                  x assumed leave rate
```

- **Annual revenue** comes from `monthly_revenue.csv`, summed over 12 months for each dealer and department. Total revenue is $839m, and Sales is 88.7% of it.
- **The share** is that dealer-department's dissatisfied share. Where a cell has fewer than 30 rated responses, the group's department share is used instead and the cell is marked.
- **Leave rate** is the share of those customers assumed to take their business elsewhere. There is **no churn data**, so these are my labelled assumptions:

| Scenario | Share used | Service + Parts leave rate | Sales leave rate |
|---|---|---|---|
| Low | dissatisfied | 5% | 1% |
| Base | dissatisfied | 10% | 2.5% |
| High | at risk (wider group) | 20% | 5% |

**Why Sales is kept out of the headline.** My first, naive method gave $10.11m, of which Sales was $7.64m (76%). That is misleading: a car already sold isn't recurring revenue. What's really at risk is a future repeat purchase or referral, which is much less certain. Sales is shown on a separate line labelled "indicative", and the headline is Service + Parts only.

**Result (annual):**

| Case | Service + Parts (headline) | Sales (indicative) |
|---|---|---|
| Low | $1.23m | $0.76m |
| **Base** | **$2.47m** | $1.91m |
| High | $7.17m | $6.15m |

**What to fix first.** Each cell's revenue at risk is split across themes using that cell's dissatisfied theme mix. Priority = frequency x severity x fixability:
- Frequency is the theme's share of dissatisfied comments.
- Severity is the share of that theme's comments that are dissatisfied.
- Fixability is my 1 to 3 judgement of how much the dealer controls it and how quickly it can change.

| Rank | Theme | Base $m | Share | Fixability |
|---|---|---|---|---|
| 1 | **Communication and updates** | 0.71 | 28.6% | 3 |
| 2 | **Wait time and turnaround** | 0.65 | 26.2% | 2 |
| 3 | Work quality and fix | 0.34 | 13.8% | 2 |
| 4 | Price and billing | 0.33 | 13.5% | 3 |
| 5 | Process and facilities | 0.28 | 11.3% | 2 |
| 6 | Staff attitude | 0.14 | 5.8% | 2 |

Work quality is less common but the most severe of the common themes (59%). The top three are the same without the fixability judgement, and the ranking doesn't depend on the leave rate. The biggest dealers by revenue at risk (base) are Parramatta ($195k), Dandenong ($185k) and Chermside ($163k).

**Confidence:** high on the ranking, **low on the dollars**.

---

## Chapter 9. What I recommend

1. **Service: set a status-update standard.** Every open job gets a call or text by an agreed time. Evidence: communication is the top theme and 28.6% of revenue at risk. Measure: its share of dissatisfied Service comments (29% now) and the Service dissatisfied rate (27.2%).
2. **Parts: tell customers about back-orders with an expected date.** Evidence: waiting is 47% of dissatisfied Parts comments. Measure: that share and the Parts dissatisfied rate (16.2%).
3. **Review the booking rollout at Parramatta and Dandenong.** Since May, 20.2% and 17.7% of their dissatisfied responses mention booking, against 3.1% elsewhere. Check call-backs and availability, and confirm the go-live date and any logging change. Measure: their dissatisfied share returning towards pre-May levels (about 17 to 18%).
4. **Sales: read the staff-attitude comments** (34% of dissatisfied Sales comments) to find the pattern. The dollar effect is indicative only.
5. **Chase the missing data:** Penrith June 2026, Toowoomba's raw Oct–Dec 2025 data (and whether it surveys Sales), Bendigo's "S" code, and confirmation of the Hunter and Ipswich dealer codes.

---

## Chapter 10. How I verified, and where the AI was wrong

The brief asked for honesty about AI. I used Claude Code to build and a separate Claude chat to review and draft; I made every decision, wrote the theme definitions, and did all hand labelling and checks.

**Where the AI went wrong, and how I caught it:**
- **Redaction bug.** The staff-name redaction was case-sensitive, and the check reused the same pattern, so it agreed with itself. **152 comments (23 dealers) reached the model with a staff first name.** Counting unlisted names for the report exposed it. Fix: case-insensitive redaction plus an independent token-by-token checker sharing no code. I authorised a relabel of the 152 comments (22 labels changed, $0.037). Lesson: a verifier must be independent of what it verifies.
- **Said the model didn't exist.** Claude Code claimed `claude-haiku-5-5` wasn't real and swapped in an older one. The pricing page showed it was real. Since then the model is never assumed: `select_model.py` lists what the API key can use.
- **Phantom duplicates.** It reported 163, then 76, colliding record IDs. An independent pandas check showed 0.
- **First dollar method** let car sales dominate, which is why D9 exists.
- **Smaller slips:** matched Springwood to Ringwood by substring, took CSV comment rows for headers, and a staff-paraphrase regex tagged first-person comments as staff.

**Other checks:** 10 cleaned rows were checked against the source spreadsheets and all matched. A fresh-clone test with no API key reproduced the silver table, the gold table and every analysis output exactly. There are 11 pytest tests with a fake client.

---

## Chapter 11. Limits and what I'd do next

**Honest limits:**
- One labeller, 120 labels; Noosa isn't in the sample.
- Leave rates and fixability are my assumptions.
- 29 of 48 headline cells use the department theme mix because the dealer cell is thin.
- Responders aren't all customers, and collection differs by dealer (cards, surveys, staff logs).
- Redaction is best effort.
- The Hunter, IPS and Bendigo "S" mappings are inferred.

**With more time:**
- **Prompt v2** with explicit rules for explaining how a vehicle works and for short "easy" comments, validated on a fresh sample.
- A **second labeller** to measure agreement, plus Noosa in the sample.
- **Real churn or repurchase data** to replace the leave-rate assumptions.
- **Confirm the booking-system story** with Parramatta and Dandenong: go-live dates and logging changes.
- **A standard submission template** for dealers, which is the real long-term fix. The pipeline is a bridge until then.

---

## The story in one paragraph

Kestrel had 52 messy spreadsheets and no answers. I profiled them, logged 161 issues, and built a config-driven pipeline that reads every row, fixes scales, dates and duplicates, removes personal data, and keeps every excluded row with a reason. I used Claude Haiku to tag 5,150 comments with a theme and sentiment, and proved it's trustworthy against 120 blind hand labels (96.7% sentiment, 85.8% theme). The analysis showed Service is the problem (27% dissatisfied), driven by customers not being kept informed and by waiting. Dissatisfaction rose over the year, mostly at two dealers that launched a booking system in May. About $2.5m a year of Service and Parts revenue is at risk (an estimate), and the fixes are cheap and concrete: status updates, back-order dates, and a booking-rollout review.
