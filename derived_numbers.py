"""
derived_numbers.py - compute the report numbers that are counts over other outputs, so every number cites a file.

Writes outputs/derived_numbers.csv: one row per number (metric, value, source, method). Counts only: no comment
text and no names are written. Run after analysis.ipynb and 04_evaluate.py. No API calls.

Staff first names (redaction gap fixed on 2026-10-28):
  - before the fix: the old 02_silver.py rule (listed names, exact case only) is re-applied to the raw comments in
    bronze, and what it left is counted: listed names in another case, and the reviewed unlisted names (hashes in
    config/redaction.yaml; found with a [STAFF]-slot rule, see ai_usage_log.md).
  - after the fix: current silver, token by token, any case.
  - the relabelling of the changed comments: outputs/relabel_redaction_fix.csv and the last live run's token use.
Run:  python derived_numbers.py
"""
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path

import openpyxl
import pandas as pd
import yaml

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent
OUT = ROOT / "outputs"
THEMES = yaml.safe_load((ROOT / "config" / "settings.yaml").read_text(encoding="utf-8"))["labels"]["themes"]
STAFF_WRITEUP_DEALERS = ["VIC03", "QLD03"]           # Essendon, Ipswich
BANNER = ("feedback/Dandenong Customer Feedback 2025-26.xlsx", "May 26", "A3")

UNLISTED = set(yaml.safe_load((ROOT / "config" / "redaction.yaml").read_text(encoding="utf-8"))["unlisted_staff_name_sha256_16"])
_spec = importlib.util.spec_from_file_location("silver_mod", ROOT / "02_silver.py")
silver_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(silver_mod)            # for redact() only (PII patterns); main() is not run

rows = []


def add(metric, value, source, method):
    rows.append({"metric": metric, "value": value, "source": source, "method": method})


def h(w):
    return hashlib.sha256(w.encode()).hexdigest()[:16]


def main():
    # ---- Q1: top theme by dealer (dealers with 30+ dissatisfied comments)
    d = pd.read_csv(OUT / "q1_theme_by_dealer.csv", index_col=0)
    add("q1_dealers_thin (<30 dissatisfied comments)", int(d["thin"].astype(bool).sum()), "outputs/q1_theme_by_dealer.csv", "thin == True")
    dd = pd.read_csv(OUT / "q1_theme_by_dealer_department.csv")
    add("q1_dealer_department_cells", len(dd), "outputs/q1_theme_by_dealer_department.csv", "cells with any dissatisfied comment")
    add("q1_dealer_department_cells_thin", int(dd["thin"].astype(bool).sum()), "outputs/q1_theme_by_dealer_department.csv", "thin == True")
    d = d[~d["thin"].astype(bool)]
    top = d[THEMES].idxmax(axis=1)
    ties = d[THEMES].apply(lambda r: int((r == r.max()).sum() > 1), axis=1)
    src = "outputs/q1_theme_by_dealer.csv"
    add("q1_dealers_with_30plus_dissatisfied", len(d), src, "dealers with thin == False")
    for t in ["Communication and updates", "Wait time and turnaround", "Work quality and fix"]:
        add(f"q1_dealers_top_theme: {t}", int((top == t).sum()), src, "primary-theme share is the dealer's largest (ties go to the first theme in settings order)")
    add("q1_dealers_with_tied_top_theme", int(ties.sum()), src, "two themes share the largest value")

    # ---- Q1: largest change in any theme share without Essendon and Ipswich
    q = pd.read_csv(OUT / "q1_theme_by_department.csv")
    a = q[q["dealers"] == "all dealers"].set_index(["department", "basis"])[THEMES]
    b = q[q["dealers"] != "all dealers"].set_index(["department", "basis"])[THEMES]
    diff = (a - b).abs().stack()
    where = diff.idxmax()
    add("q1_max_share_change_without_essendon_ipswich_pts", round(100 * diff.max(), 1), "outputs/q1_theme_by_department.csv",
        f"max |all dealers - without| over departments, bases and themes; at {where[0]} / {where[1]} / {where[2]}")

    # ---- voice tag: share of staff write-ups not tagged
    v = pd.read_csv(OUT / "evaluation" / "voice_check.csv", index_col=0)
    staff_total = int(v.loc["staff"].sum())
    add("voice_staff_writeups_untagged_share_pct", round(100 * v.loc["staff", "customer"] / staff_total, 1),
        "outputs/evaluation/voice_check.csv", f"hand label staff, tagged customer, of {staff_total} hand-labelled staff rows")

    # ---- extra check sheet: available AI-labelled comments per theme outside the hand-checked rows
    ex = pd.read_excel(ROOT / "labelling" / "extra_check.xlsx", sheet_name="Labels", dtype=str)
    lab = pd.read_csv(ROOT / "data" / "silver_labels" / "labels.csv", dtype=str, keep_default_na=False)
    lab_ex = lab.set_index("feedback_id").loc[ex["feedback_id"], "primary_theme"]
    for t in ["Vehicle or product", "Other"]:
        add(f"extra_check_rows: {t}", int((lab_ex == t).sum()), "labelling/extra_check.xlsx + data/silver_labels/labels.csv",
            "rows in the blind sheet whose AI primary theme is this")
        add(f"ai_primary_theme_comments: {t}", int((lab["primary_theme"] == t).sum()), "data/silver_labels/labels.csv", "all labelled comments")

    # ---- staff first names left in comment text
    s = pd.read_csv(ROOT / "data" / "silver" / "feedback_silver.csv", dtype=str, keep_default_na=False)
    c = s[(s["excluded"] == "False") & (s["has_text"] == "True")]
    cust = c["voice"] == "customer"
    staff = pd.read_csv(ROOT / "data" / "bronze" / "staff_names.csv")["first_name"].tolist()
    listed = {n.lower() for n in staff}

    def tokens(t):          # letter runs, lower case, no regex (same idea as the 02_silver check)
        return "".join(ch.lower() if ch.isalpha() else " " for ch in t).split()

    # BEFORE the fix: rebuild what the old rule left, from the raw comment in bronze. The old rule replaced
    # listed names only, and only in their exact case.
    b = pd.read_csv(ROOT / "data" / "bronze" / "bronze_rows.csv", dtype=str, keep_default_na=False)
    key = ["source_file", "source_sheet", "source_row"]
    cb = c.merge(b[b["row_class"] == "data"][key + ["comment_raw"]], on=key, how="left", validate="1:1")
    assert cb["comment_raw"].notna().all()
    old_re = re.compile(r"\b(?:" + "|".join(map(re.escape, sorted(staff, key=len, reverse=True))) + r")\b")
    old_left = [old_re.sub(" ", silver_mod.redact(t)[0]) for t in cb["comment_raw"]]
    listed_lower = pd.Series([any(w in listed for w in tokens(t)) for t in old_left], index=c.index)
    unlisted_hit = pd.Series([any(h(w) in UNLISTED for w in tokens(t)) for t in old_left], index=c.index)
    any_hit = listed_lower | unlisted_hit
    src = "data/bronze/bronze_rows.csv (comment_raw, old case-sensitive rule re-applied) + data/silver/feedback_silver.csv"
    add("before_fix: comments with a listed staff name left (not in exact case)", int(listed_lower.sum()), src, "included rows with text")
    add("before_fix: comments with an unlisted staff name", int(unlisted_hit.sum()), src, f"{len(UNLISTED)} reviewed names, hashed in config/redaction.yaml")
    add("before_fix: comments with any staff first name left", int(any_hit.sum()), src, "either of the two above")
    add("before_fix: of which customer voice (sent to the model)", int((any_hit & cust).sum()), src, "voice == customer")
    add("before_fix: dealers affected", int(c.loc[any_hit, "dealer_code"].nunique()), src, "distinct dealer_code")
    add("comments_with_text_included", len(c), "data/silver/feedback_silver.csv", "denominator")
    # AFTER the fix: current silver, token by token
    after = c["comment_clean"].map(lambda t: any(w in listed or h(w) in UNLISTED for w in tokens(t)))
    add("after_fix: comments with any staff first name left", int(after.sum()), "data/silver/feedback_silver.csv", "token-by-token, any case")
    r = pd.read_csv(OUT / "relabel_redaction_fix.csv", dtype=str, keep_default_na=False)
    changed = (r["primary_before"] != r["primary_after"]) | (r["secondary_before"] != r["secondary_after"]) | (r["sentiment_before"] != r["sentiment_after"])
    src = "outputs/relabel_redaction_fix.csv"
    add("relabelled_after_fix", len(r), src, "comments whose redacted text changed")
    add("relabelled_primary_theme_changed", int((r["primary_before"] != r["primary_after"]).sum()), src, "")
    add("relabelled_secondary_theme_changed", int((r["secondary_before"] != r["secondary_after"]).sum()), src, "")
    add("relabelled_sentiment_changed", int((r["sentiment_before"] != r["sentiment_after"]).sum()), src, "")
    add("relabelled_any_label_changed", int(changed.sum()), src, "primary, secondary or sentiment")
    hist = [json.loads(l) for l in (ROOT / "data" / "silver_labels" / "run_history.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    fix = hist[-1]
    cfg = yaml.safe_load((ROOT / "config" / "settings.yaml").read_text(encoding="utf-8"))
    price = cfg["pricing"]["by_model"][cfg["llm"]["model_display_name"]]
    u = fix["usage_this_run"]
    add("relabel_run_api_calls", fix["api_calls_this_run"], "data/silver_labels/run_history.jsonl (last live run)", "")
    add("relabel_run_cost_usd", round(u["input_tokens"] / 1e6 * price["input"] + u["output_tokens"] / 1e6 * price["output"], 3),
        "data/silver_labels/run_history.jsonl x config/settings.yaml pricing", f"{u['input_tokens']} in / {u['output_tokens']} out tokens")

    # ---- cost of the full live labelling run: tokens from its run log x the price in settings
    run = json.loads((ROOT / "data" / "silver_labels" / "run_log_live_full_2026-10-28.json").read_text(encoding="utf-8"))
    u = run["usage_this_run"]
    add("labelling_full_run_cost_usd", round(u["input_tokens"] / 1e6 * price["input"] + u["output_tokens"] / 1e6 * price["output"], 2),
        "data/silver_labels/run_log_live_full_2026-10-28.json x config/settings.yaml pricing",
        f"{u['input_tokens']} input and {u['output_tokens']} output tokens at ${price['input']}/${price['output']} per M; excludes ~68 trial and check calls")
    add("labelling_full_run_api_calls", run["api_calls_this_run"], "data/silver_labels/run_log_live_full_2026-10-28.json", "")
    add("labelling_full_run_failures", run["new_failures"], "data/silver_labels/run_log_live_full_2026-10-28.json", "")

    # ---- the booking-system go-live date, from the source workbook banner
    f, sheet, cell = BANNER
    wb = openpyxl.load_workbook(ROOT / f, read_only=True)
    text = wb[sheet][cell].value
    wb.close()
    m = re.search(r"went live (\d{1,2} [A-Z][a-z]+)", text)
    add("booking_system_go_live_date (Dandenong banner)", m.group(1), f"{f}, sheet '{sheet}', cell {cell}", "quoted from the banner text")

    out = pd.DataFrame(rows)
    out.to_csv(OUT / "derived_numbers.csv", index=False)
    print(out[["metric", "value"]].to_string(index=False))


if __name__ == "__main__":
    main()
