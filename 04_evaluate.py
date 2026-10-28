"""
04_evaluate.py - measure the AI labels against the hand labels (SPEC section 10), and run the D2 Ringwood test.

Reads (read-only):
  labelling/labelling_sheet.xlsx   tabs Labels (my_primary_theme, my_secondary_theme, my_sentiment) and Voice_check (my_voice)
  data/silver_labels/labels.csv    output of 03_label.py
  data/silver/feedback_silver.csv  for the voice tag and the Ringwood scores

Writes outputs/evaluation/:
  evaluation_report.md     all results in one readable page
  sentiment_confusion.csv, theme_confusion.csv, per_theme.csv, per_sentiment.csv
  errors.csv               10 real disagreements, with an automatic hint and an empty reviewer_reason column
  voice_check.csv          voice tag vs hand label
  ringwood_d2.csv          Ringwood 1-10 score x AI sentiment (V1 / D2)

Rows the labeller left blank are not scored and are counted in the report. No LLM calls.
Run:  python 04_evaluate.py [--sheet PATH] [--labels PATH] [--out DIR]
"""
import argparse
import math
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent


# --------------------------------------------------------------------------------------
# Metrics
# --------------------------------------------------------------------------------------
def cohen_kappa(a, b):
    a, b = list(a), list(b)
    n = len(a)
    if n == 0:
        return float("nan")
    cats = sorted(set(a) | set(b))
    po = sum(x == y for x, y in zip(a, b)) / n
    pe = sum((a.count(c) / n) * (b.count(c) / n) for c in cats)
    return float("nan") if pe == 1 else (po - pe) / (1 - pe)


def wilson(k, n, z=1.96):
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)


def per_class(human, ai, classes):
    rows = []
    for c in classes:
        tp = sum((h == c) and (a == c) for h, a in zip(human, ai))
        fp = sum((h != c) and (a == c) for h, a in zip(human, ai))
        fn = sum((h == c) and (a != c) for h, a in zip(human, ai))
        p = tp / (tp + fp) if tp + fp else float("nan")
        r = tp / (tp + fn) if tp + fn else float("nan")
        f1 = 2 * p * r / (p + r) if p + r and not math.isnan(p) and not math.isnan(r) else float("nan")
        rows.append({"class": c, "support_human": tp + fn, "predicted_ai": tp + fp, "precision": p, "recall": r, "f1": f1})
    return pd.DataFrame(rows)


def confusion(human, ai, classes):
    t = pd.crosstab(pd.Series(human, name="human"), pd.Series(ai, name="ai"))
    return t.reindex(index=classes, columns=classes, fill_value=0)


def hint(r):
    """Automatic first guess at why a pair disagrees; the reviewer writes the real reason."""
    out = []
    if r.human_primary != r.ai_primary:
        if r.ai_primary == r.human_secondary or r.human_primary == r.ai_secondary:
            out.append("competing themes: same two themes, different primary")
        elif r.human_primary == "Other" or r.ai_primary == "Other":
            out.append("vague comment: one side chose Other")
        else:
            out.append("different theme")
    if r.human_sentiment != r.ai_sentiment:
        if "mixed" in (r.human_sentiment, r.ai_sentiment):
            out.append("mixed vs single polarity")
        elif "neutral" in (r.human_sentiment, r.ai_sentiment):
            out.append("neutral vs polar")
        else:
            out.append("opposite polarity (possible sarcasm or misread)")
    if pd.notna(r.ai_confidence) and float(r.ai_confidence) < 0.6:
        out.append(f"low model confidence ({float(r.ai_confidence):.2f})")
    return "; ".join(out)


def fmt(x, pct=True):
    return "n/a" if x is None or (isinstance(x, float) and math.isnan(x)) else (f"{100 * x:.1f}%" if pct else f"{x:.2f}")


def md(df, index=False):
    d = df.reset_index() if index else df
    cols = [str(c) for c in d.columns]
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in d.itertuples(index=False):
        lines.append("| " + " | ".join("" if pd.isna(v) else (f"{v:.2f}" if isinstance(v, float) else str(v)).replace("|", "/").replace("\n", " ") for v in r) + " |")
    return "\n".join(lines)


# --------------------------------------------------------------------------------------
def ringwood_d2(silver, labels):
    """V1 / D2: Ringwood 1-10 score x AI sentiment."""
    r = silver[(silver["excluded"] == "False") & (silver["rating_scale"] == "num_1_10")]
    r = r.merge(labels[labels["label_status"] == "labelled"][["feedback_id", "sentiment"]], on="feedback_id")
    if r.empty:
        return pd.DataFrame(), {}
    r["score"] = r["rating_raw"].astype(int)
    t = pd.crosstab(r["score"], r["sentiment"]).reindex(index=range(1, 11), fill_value=0)
    for c in ("positive", "neutral", "negative", "mixed"):
        if c not in t:
            t[c] = 0
    t = t[["negative", "mixed", "neutral", "positive"]]
    t["n"] = t.sum(axis=1)
    t["negative_share"] = (t["negative"] / t["n"]).where(t["n"] > 0)
    t["negative_or_mixed_share"] = ((t["negative"] + t["mixed"]) / t["n"]).where(t["n"] > 0)
    low = t.loc[1:4]
    all_r = silver[(silver["excluded"] == "False") & (silver["rating_scale"] == "num_1_10") & (silver["rating_raw"] != "")]
    sc = all_r["rating_raw"].astype(int)
    res = {
        "labelled_rows": int(t["n"].sum()),
        "share_negative_1_4": low["negative"].sum() / low["n"].sum() if low["n"].sum() else float("nan"),
        "share_negative_or_mixed_1_4": (low["negative"].sum() + low["mixed"].sum()) / low["n"].sum() if low["n"].sum() else float("nan"),
        "negative_share_5": t.loc[5, "negative_share"], "negative_share_6": t.loc[6, "negative_share"],
        "n_5": int(t.loc[5, "n"]), "n_6": int(t.loc[6, "n"]),
        "headline_at_risk_le5": (sc <= 5).mean(), "sensitivity_at_risk_le6": (sc <= 6).mean(), "ringwood_rows": len(sc),
    }
    res["strict_1_4_mostly_negative"] = bool(res["share_negative_or_mixed_1_4"] > 0.5)
    return t.reset_index(), res


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheet", default=str(ROOT / "labelling" / "labelling_sheet.xlsx"))
    ap.add_argument("--labels", default=str(ROOT / "data" / "silver_labels" / "labels.csv"))
    ap.add_argument("--silver", default=str(ROOT / "data" / "silver" / "feedback_silver.csv"))
    ap.add_argument("--out", default=str(ROOT / "outputs" / "evaluation"))
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    hum = pd.read_excel(args.sheet, sheet_name="Labels", dtype=str).fillna("")
    voice_sheet = pd.read_excel(args.sheet, sheet_name="Voice_check", dtype=str).fillna("")
    themes = ["Staff attitude", "Communication and updates", "Wait time and turnaround", "Price and billing",
              "Work quality and fix", "Vehicle or product", "Process and facilities", "Other"]
    sents = ["positive", "neutral", "negative", "mixed"]

    for c in hum.columns:
        hum[c] = hum[c].str.strip()
    done = hum[(hum["my_primary_theme"] != "") & (hum["my_sentiment"] != "")]
    if done.empty:
        sys.exit("No hand labels yet (my_primary_theme and my_sentiment are empty in every row).")
    bad = done[~done["my_primary_theme"].isin(themes) | ~done["my_sentiment"].isin(sents)
               | ~done["my_secondary_theme"].isin(themes + [""])]
    if len(bad):
        sys.exit(f"{len(bad)} hand-label rows have values outside the allowed lists, e.g. feedback_id {bad['feedback_id'].iloc[0]}")

    ai = pd.read_csv(args.labels, dtype=str, keep_default_na=False)
    silver = pd.read_csv(args.silver, dtype=str, keep_default_na=False)
    j = done.merge(ai, on="feedback_id", how="left")
    no_ai = j[j["label_status"] != "labelled"]
    j = j[j["label_status"] == "labelled"].copy()
    j = j.rename(columns={"my_primary_theme": "human_primary", "my_secondary_theme": "human_secondary",
                          "my_sentiment": "human_sentiment", "primary_theme": "ai_primary",
                          "secondary_theme": "ai_secondary", "sentiment": "ai_sentiment", "confidence": "ai_confidence"})
    n = len(j)
    if n == 0:
        sys.exit("None of the hand-labelled rows has an AI label yet (run 03_label.py).")

    s_ok = (j["human_sentiment"] == j["ai_sentiment"])
    t_ok = (j["human_primary"] == j["ai_primary"])
    t_len = t_ok | (j["ai_primary"] == j["human_secondary"]) | ((j["human_primary"] == j["ai_secondary"]) & (j["ai_secondary"] != ""))
    res = {
        "hand_labelled": len(done), "sheet_rows": len(hum), "blank_in_sheet": len(hum) - len(done),
        "without_ai_label": len(no_ai), "scored": n,
        "sentiment_accuracy": s_ok.mean(), "sentiment_ci": wilson(s_ok.sum(), n),
        "sentiment_kappa": cohen_kappa(j["human_sentiment"], j["ai_sentiment"]),
        "theme_accuracy": t_ok.mean(), "theme_ci": wilson(t_ok.sum(), n),
        "theme_accuracy_lenient": t_len.mean(),
        "theme_kappa": cohen_kappa(j["human_primary"], j["ai_primary"]),
        "both_correct": (s_ok & t_ok).mean(),
    }
    sc = confusion(j["human_sentiment"], j["ai_sentiment"], sents)
    tc = confusion(j["human_primary"], j["ai_primary"], themes)
    pt = per_class(list(j["human_primary"]), list(j["ai_primary"]), themes)
    ps = per_class(list(j["human_sentiment"]), list(j["ai_sentiment"]), sents)
    sc.to_csv(out / "sentiment_confusion.csv")
    tc.to_csv(out / "theme_confusion.csv")
    pt.to_csv(out / "per_theme.csv", index=False)
    ps.to_csv(out / "per_sentiment.csv", index=False)

    wrong = j[~s_ok | ~t_ok].copy()
    wrong["hint"] = [hint(r) for r in wrong.itertuples()]
    errs = wrong.sample(min(10, len(wrong)), random_state=args.seed) if len(wrong) else wrong
    errs = errs.assign(reviewer_reason="")[["feedback_id", "dealer_code", "department", "comment_clean", "human_primary", "human_secondary",
                                            "ai_primary", "ai_secondary", "human_sentiment", "ai_sentiment", "ai_confidence", "hint", "reviewer_reason"]]
    errs.to_csv(out / "errors.csv", index=False)

    # voice tag check
    v = voice_sheet[voice_sheet["my_voice"].str.strip() != ""].merge(silver[["feedback_id", "voice"]], on="feedback_id", how="left")
    vres = {}
    if len(v):
        hv = v["my_voice"].str.strip().str.lower()
        tag = v["voice"].map({"staff_paraphrased": "staff", "customer": "customer"}).fillna("other")
        vres = {"n": len(v), "agreement": (hv == tag).mean(),
                "staff_tag_precision": ((tag == "staff") & (hv == "staff")).sum() / max((tag == "staff").sum(), 1),
                "staff_tag_recall": ((tag == "staff") & (hv == "staff")).sum() / max((hv == "staff").sum(), 1)}
        pd.crosstab(hv.rename("my_voice"), tag.rename("tag")).to_csv(out / "voice_check.csv")

    rt, rres = ringwood_d2(silver, ai)
    if len(rt):
        rt.to_csv(out / "ringwood_d2.csv", index=False)

    lines = [
        "# Evaluation: AI labels vs hand labels",
        "",
        f"Hand-labelled rows scored: **{n}** (sheet rows {res['sheet_rows']}, left blank {res['blank_in_sheet']}, "
        f"labelled but no AI label {res['without_ai_label']}). Limits: one labeller, small sample, Noosa (QLD05) not in the sample.",
        "",
        "| Measure | Value | 95% CI |",
        "|---|---|---|",
        f"| Sentiment accuracy | {fmt(res['sentiment_accuracy'])} | {fmt(res['sentiment_ci'][0])} - {fmt(res['sentiment_ci'][1])} |",
        f"| Sentiment Cohen's kappa | {fmt(res['sentiment_kappa'], False)} | |",
        f"| Primary theme accuracy | {fmt(res['theme_accuracy'])} | {fmt(res['theme_ci'][0])} - {fmt(res['theme_ci'][1])} |",
        f"| Theme accuracy, lenient (AI primary is either human theme, or vice versa) | {fmt(res['theme_accuracy_lenient'])} | |",
        f"| Primary theme Cohen's kappa | {fmt(res['theme_kappa'], False)} | |",
        f"| Both theme and sentiment correct | {fmt(res['both_correct'])} | |",
        "",
        "## Per theme (primary)", "", md(pt), "",
        "## Per sentiment", "", md(ps), "",
        "## Sentiment confusion (rows = human, columns = AI)", "", md(sc, index=True), "",
        "## Theme confusion (rows = human, columns = AI)", "", md(tc, index=True), "",
        "## 10 disagreements", "",
        "`hint` is automatic; `reviewer_reason` is for the human reviewer (see errors.csv).", "",
        md(errs.drop(columns=["reviewer_reason"])), "",
        "## Voice tag check (Voice_check tab)", "",
        (f"{vres['n']} rows: agreement {fmt(vres['agreement'])}, staff-tag precision {fmt(vres['staff_tag_precision'])}, "
         f"recall {fmt(vres['staff_tag_recall'])}" if vres else "Voice_check tab not filled yet."), "",
        "## D2 / V1: Ringwood 1-10 score vs AI sentiment", "",
    ]
    if rres:
        lines += [md(rt), "",
                  f"- Scores 1-4 negative or mixed: {fmt(rres['share_negative_or_mixed_1_4'])} (negative only {fmt(rres['share_negative_1_4'])}); "
                  f"strict definition supported: {rres['strict_1_4_mostly_negative']}",
                  f"- Negative share at 5: {fmt(rres['negative_share_5'])} (n={rres['n_5']}); at 6: {fmt(rres['negative_share_6'])} (n={rres['n_6']})",
                  f"- Ringwood at-risk share: headline <=5 {fmt(rres['headline_at_risk_le5'])} vs sensitivity <=6 {fmt(rres['sensitivity_at_risk_le6'])} "
                  f"(all {rres['ringwood_rows']} rated 1-10 rows). The headline rule stays <=5 (D1); the gap is the likely understatement.",
                  "- Uses AI sentiment on every labelled Ringwood comment, not only the hand-labelled sample; its reliability is the sentiment accuracy above."]
    else:
        lines.append("No AI labels for Ringwood 1-10 rows yet.")
    (out / "evaluation_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:14]))
    return res, vres, rres


if __name__ == "__main__":
    main()
