"""
evaluate_extra_check.py - score the AI on the two themes the 120-row sample never contained.

Reads the author's blind labels in labelling/extra_check.xlsx (read-only) and the AI labels in
data/silver_labels/labels.csv. The sheet holds every AI-labelled Vehicle or product comment and 20 of the
Other comments, outside the 150 hand-checked rows (make_extra_check.py).

Writes outputs/evaluation/:
  extra_check_rows.csv       one row per comment: human and AI labels, agreement flags (no comment text)
  extra_check_summary.csv    per AI theme: n, primary agreement (= precision of that AI theme on this sample),
                             sentiment agreement, both, with 95% Wilson intervals
  extra_check_report.md      the summary plus every disagreement with its (redacted) comment text
No API calls.   Run:  python evaluate_extra_check.py
"""
import importlib.util
import sys
from pathlib import Path

import pandas as pd

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent
OUT = ROOT / "outputs" / "evaluation"
SHEET = ROOT / "labelling" / "extra_check.xlsx"
CHECK_THEMES = ["Vehicle or product", "Other"]
_spec = importlib.util.spec_from_file_location("ev", ROOT / "04_evaluate.py")
ev = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ev)


def main():
    h = pd.read_excel(SHEET, sheet_name="Labels", dtype=str).fillna("")
    if (h["my_primary_theme"] == "").any() or (h["my_sentiment"] == "").any():
        sys.exit(f"{SHEET.name}: {int((h['my_primary_theme'] == '').sum())} rows without a primary theme or sentiment")
    ai = pd.read_csv(ROOT / "data" / "silver_labels" / "labels.csv", dtype=str, keep_default_na=False)
    d = h.merge(ai[["feedback_id", "label_status", "primary_theme", "secondary_theme", "sentiment", "confidence"]],
                on="feedback_id", how="left", validate="1:1")
    assert (d["label_status"] == "labelled").all() and d["primary_theme"].isin(CHECK_THEMES).all()
    d["primary_agree"] = d["my_primary_theme"] == d["primary_theme"]
    d["sentiment_agree"] = d["my_sentiment"] == d["sentiment"]
    d["both_agree"] = d["primary_agree"] & d["sentiment_agree"]
    d["either_theme_agree"] = d["primary_agree"] | (d["my_secondary_theme"] == d["primary_theme"]) | \
        ((d["secondary_theme"] != "") & (d["secondary_theme"] == d["my_primary_theme"]))

    rows = []
    for t in CHECK_THEMES:
        g = d[d["primary_theme"] == t]
        r = {"ai_primary_theme": t, "n": len(g)}
        for k in ["primary_agree", "sentiment_agree", "both_agree", "either_theme_agree"]:
            lo, hi = ev.wilson(int(g[k].sum()), len(g))
            r.update({f"{k}_n": int(g[k].sum()), f"{k}_share": round(g[k].mean(), 3), f"{k}_ci_low": round(lo, 3), f"{k}_ci_high": round(hi, 3)})
        r["human_primary_when_disagree"] = "; ".join(f"{k} {v}" for k, v in g.loc[~g["primary_agree"], "my_primary_theme"].value_counts().items())
        rows.append(r)
    summary = pd.DataFrame(rows)
    summary.to_csv(OUT / "extra_check_summary.csv", index=False)
    keep = ["feedback_id", "dealer_code", "department", "my_primary_theme", "my_secondary_theme", "my_sentiment",
            "primary_theme", "secondary_theme", "sentiment", "confidence", "primary_agree", "sentiment_agree", "both_agree", "either_theme_agree"]
    d[keep].rename(columns={"primary_theme": "ai_primary_theme", "secondary_theme": "ai_secondary_theme", "sentiment": "ai_sentiment",
                            "confidence": "ai_confidence"}).to_csv(OUT / "extra_check_rows.csv", index=False)

    lines = ["# Extra check: AI-labelled Vehicle or product and Other", "",
             f"Blind hand labels on {len(d)} comments outside the 120 + 30 hand-checked rows (`labelling/extra_check.xlsx`). "
             "Precision of an AI theme = share of the comments the AI gave that primary theme where the hand label agrees.", "",
             "| AI primary theme | n | Primary agrees (precision) | 95% CI | Sentiment agrees | Both | Either theme matches |", "|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['ai_primary_theme']} | {r['n']} | {r['primary_agree_n']} ({100 * r['primary_agree_share']:.0f}%) | "
                     f"{100 * r['primary_agree_ci_low']:.0f}-{100 * r['primary_agree_ci_high']:.0f}% | {r['sentiment_agree_n']} | {r['both_agree_n']} | {r['either_theme_agree_n']} |")
    lines += ["", "## Disagreements (comment text is the redacted text the model saw)", "",
              "| feedback_id | Department | Comment | Hand primary / secondary / sentiment | AI primary / secondary / sentiment | Differs on |", "|---|---|---|---|---|---|"]
    for _, r in d[~d["both_agree"]].sort_values(["primary_theme", "feedback_id"]).iterrows():
        what = " and ".join(x for x, ok in (("theme", r["primary_agree"]), ("sentiment", r["sentiment_agree"])) if not ok)
        cell = lambda *v: " / ".join(x or "-" for x in v)
        lines.append(f"| {r['feedback_id']} | {r['department']} | {r['comment_clean'].replace('|', '/')} | "
                     f"{cell(r['my_primary_theme'], r['my_secondary_theme'], r['my_sentiment'])} | "
                     f"{cell(r['primary_theme'], r['secondary_theme'], r['sentiment'])} | {what} |")
    (OUT / "extra_check_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(summary[["ai_primary_theme", "n", "primary_agree_n", "primary_agree_share", "primary_agree_ci_low", "primary_agree_ci_high",
                   "sentiment_agree_n", "both_agree_n", "either_theme_agree_n", "human_primary_when_disagree"]].to_string(index=False))
    print(f"disagreements (theme or sentiment): {int((~d['both_agree']).sum())} of {len(d)}")


if __name__ == "__main__":
    main()
