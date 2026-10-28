"""
05_gold.py - silver + AI labels + monthly revenue.

Outputs (data/gold/):
  feedback_gold.csv        every silver row with its AI label columns (label_status says why a row has none)
  dealer_month_dept.csv    one row per dealer x month x department from monthly_revenue.csv (24 x 12 x 3),
                           with revenue, transactions and feedback metrics from included silver rows

Gaps show as missing, not zero (D5): a dealer-month with no feedback rows at all gets empty
(NaN) feedback metrics, including responses, and a gap_reason. A department with no rows inside a
dealer-month that does have feedback gets responses = 0 and empty shares.

Run:  python 05_gold.py [--labels PATH] [--out DIR] [--no-labels]
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
DEPTS = {"Sales": ("vehicles_sold", "sales_revenue_aud"), "Service": ("service_jobs", "service_revenue_aud"),
         "Parts": ("parts_transactions", "parts_revenue_aud")}
GAP_REASONS = {  # Decisions_Log D5, Data_Requests R1-R3
    ("QLD06", "2025-10"): "D5: Toowoomba Q4 2025 supplied as an aggregate summary only (R1); Sales not in the summary at all (R2)",
    ("QLD06", "2025-11"): "D5: Toowoomba Q4 2025 supplied as an aggregate summary only (R1); Sales not in the summary at all (R2)",
    ("QLD06", "2025-12"): "D5: Toowoomba Q4 2025 supplied as an aggregate summary only (R1); Sales not in the summary at all (R2)",
    ("NSW02", "2026-06"): "D5: Penrith 'Jun 26' tab is a copy of July; June 2026 not supplied (R3)",
}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--silver", default=str(ROOT / "data" / "silver" / "feedback_silver.csv"))
    ap.add_argument("--labels", default=str(ROOT / "data" / "silver_labels" / "labels.csv"))
    ap.add_argument("--out", default=str(ROOT / "data" / "gold"))
    ap.add_argument("--no-labels", action="store_true", help="build without AI labels (label columns empty)")
    args = ap.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    silver = pd.read_csv(args.silver, dtype=str, keep_default_na=False)
    if Path(args.labels).exists() and not args.no_labels:
        labels = pd.read_csv(args.labels, dtype=str, keep_default_na=False)
        if set(labels["feedback_id"]) != set(silver["feedback_id"]):
            sys.exit("labels.csv does not cover exactly the silver rows: rerun 03_label.py")
    elif args.no_labels:
        labels = pd.DataFrame({"feedback_id": silver["feedback_id"], "label_status": "not_run"})
    else:
        sys.exit(f"{args.labels} not found. Run 03_label.py first, or pass --no-labels.")
    gold = silver.merge(labels, on="feedback_id", how="left", validate="one_to_one")
    gold.to_csv(out / "feedback_gold.csv", index=False)

    # ---- dealer x month x department panel ------------------------------------------------
    rev = pd.read_csv(ROOT / "reference" / "monthly_revenue.csv")
    dealers = pd.read_csv(ROOT / "reference" / "dealerships.csv").set_index("dealer_code")
    panel = pd.concat([rev[["dealer_code", "month"]].assign(department=d, transactions=rev[t], revenue_aud=rev[r])
                       for d, (t, r) in DEPTS.items()], ignore_index=True)

    inc = gold[gold["excluded"] == "False"].copy()
    inc["score"] = pd.to_numeric(inc["score_norm"], errors="coerce")
    inc["dis"] = inc["dissatisfied"].map({"True": 1.0, "False": 0.0})
    inc["risk"] = inc["at_risk"].map({"True": 1.0, "False": 0.0})
    g = inc.groupby(["dealer_code", "month", "department"])
    fb = pd.DataFrame({
        "responses": g.size(), "rated": g["score"].count(),
        "dissatisfied_n": g["dis"].sum(), "at_risk_n": g["risk"].sum(), "mean_score": g["score"].mean().round(1),
        "with_text": g["has_text"].apply(lambda s: (s == "True").sum()),
        "ai_labelled": g["label_status"].apply(lambda s: (s == "labelled").sum()),
    }).reset_index()
    panel = panel.merge(fb, on=["dealer_code", "month", "department"], how="left")
    count_cols = ["responses", "rated", "dissatisfied_n", "at_risk_n", "with_text", "ai_labelled"]

    has_any = inc.groupby(["dealer_code", "month"]).size()
    reasons = []
    for r in panel.itertuples():
        key = (r.dealer_code, r.month)
        closed = dealers.loc[r.dealer_code, "closed_date"]
        if key in has_any.index:
            reasons.append("")
        elif isinstance(closed, str) and r.month > closed[:7]:
            reasons.append(f"site closed {closed}; no trading")
        else:
            reasons.append(GAP_REASONS.get(key, "no feedback rows supplied for this dealer-month"))
    panel["gap_reason"] = reasons
    gap = panel["gap_reason"] != ""
    # dealer-month with data: a department with no rows is a real zero count
    panel.loc[~gap, count_cols] = panel.loc[~gap, count_cols].fillna(0)
    panel.loc[gap, count_cols] = np.nan                      # gap: missing, never zero
    panel["dissatisfied_share"] = (panel["dissatisfied_n"] / panel["rated"]).where(panel["rated"] > 0).round(4)
    panel["at_risk_share"] = (panel["at_risk_n"] / panel["rated"]).where(panel["rated"] > 0).round(4)
    panel = panel.sort_values(["dealer_code", "month", "department"])
    panel.to_csv(out / "dealer_month_dept.csv", index=False)

    # ---- checks ------------------------------------------------------------------------------
    def cells(d, ms):
        return panel[(panel["dealer_code"] == d) & panel["month"].isin(ms)]
    pen, toow = cells("NSW02", ["2026-06"]), cells("QLD06", ["2025-10", "2025-11", "2025-12"])
    checks = {
        "panel = 24 dealers x 12 months x 3 departments": len(panel) == 24 * 12 * 3,
        "gold rows == silver rows": len(gold) == len(silver),
        "Penrith 2026-06 responses missing (NaN), not zero": bool(pen["responses"].isna().all() and len(pen) == 3),
        "Toowoomba 2025-10..12 responses missing (NaN), not zero": bool(toow["responses"].isna().all() and len(toow) == 9),
        "gap months still carry revenue": bool((pen["revenue_aud"] > 0).all() and (toow["revenue_aud"] > 0).all()),
        "every gap has a reason and no zero response count": bool(panel.loc[gap, "responses"].isna().all()),
        "included silver rows all land in the panel": int(panel["responses"].sum()) == len(inc),
    }
    print(f"gold rows {len(gold)} | panel rows {len(panel)} | gap cells {int(gap.sum())} "
          f"({panel.loc[gap, ['dealer_code', 'month']].drop_duplicates().shape[0]} dealer-months)")
    print(panel.loc[gap].groupby("gap_reason")[["dealer_code", "month"]].apply(
        lambda d: ", ".join(sorted({f"{a} {b}" for a, b in d.itertuples(index=False)}))).to_string())
    for k, v in checks.items():
        print(f"  [{'PASS' if v else 'FAIL'}] {k}")
    if not all(checks.values()):
        sys.exit(1)


if __name__ == "__main__":
    main()
