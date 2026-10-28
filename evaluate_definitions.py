"""
evaluate_definitions.py - the V2 check from the Verification_Plan (decision D1).

Does the "dissatisfied" (score < 40) and "at risk" (score <= 50) definition agree with the AI's sentiment label
at least as well as the alternatives? And do dealer and department rankings change between the two?
Uses only data/gold/feedback_gold.csv (included, AI-labelled comments that also have a score) and the Q1 tables.
The AI sentiment is a check on the definitions, never a target to tune them to (D1).

Writes outputs/evaluation/:
  v2_sentiment_by_score.csv   AI sentiment shares at each score level: 5-point scales pooled, Tamworth Bad/OK/Good, Ringwood 1-10
  v2_cutoff_agreement.csv     precision, recall and F1 of four score cutoffs against AI negative, and against negative or mixed
  v2_rank_comparison.csv      each dealer's rank by dissatisfied share and by at-risk share
No API calls.   Run after 05_gold.py and analysis.ipynb:  python evaluate_definitions.py
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "outputs" / "evaluation"
CUTOFFS = [("below 25 (1 of 5)", lambda s: s < 25), ("below 40 (strict, D1)", lambda s: s < 40),
           ("50 or below (at risk, D1)", lambda s: s <= 50), ("75 or below (4 of 5)", lambda s: s <= 75)]


def prf(flag, target):
    tp = int((flag & target).sum())
    p = tp / flag.sum() if flag.sum() else float("nan")
    r = tp / target.sum() if target.sum() else float("nan")
    return p, r, (2 * p * r / (p + r) if p + r else float("nan"))


def main():
    g = pd.read_csv(ROOT / "data" / "gold" / "feedback_gold.csv", dtype=str, keep_default_na=False)
    g = g[(g["excluded"] == "False") & (g["label_status"] == "labelled")].copy()
    g["score"] = pd.to_numeric(g["score_norm"], errors="coerce")
    g = g[g["score"].notna()].copy()
    neg, negmix = g["sentiment"] == "negative", g["sentiment"].isin(["negative", "mixed"])

    # ---- sentiment at each score level
    rows = []
    five = g[g["rating_scale"].isin(["num_1_5", "labels_1_5", "stars_1_5"])]
    for sc, d in five.groupby("score"):
        rows.append(("5-point scales pooled", f"{int(sc / 25) + 1} of 5", d))
    for lab, d in g[g["rating_scale"] == "labels_bad_ok_good"].groupby("rating_raw"):
        rows.append(("Tamworth Bad / OK / Good", lab, d))
    for sc, d in g[g["rating_scale"] == "num_1_10"].groupby(g["rating_raw"].astype(float, errors="ignore")):
        rows.append(("Ringwood 1-10", f"{int(float(sc))} of 10", d))
    by = pd.DataFrame([{"scale": a, "level": b, "n": len(d), "negative": (d["sentiment"] == "negative").mean(),
                        "mixed": (d["sentiment"] == "mixed").mean(), "neutral": (d["sentiment"] == "neutral").mean(),
                        "positive": (d["sentiment"] == "positive").mean(),
                        "negative_or_mixed": d["sentiment"].isin(["negative", "mixed"]).mean()} for a, b, d in rows])
    by.to_csv(OUT / "v2_sentiment_by_score.csv", index=False, float_format="%.4f")

    # ---- cutoffs against AI sentiment
    ag = []
    for name, f in CUTOFFS:
        flag = f(g["score"])
        r = {"cutoff": name, "flagged_n": int(flag.sum()), "flagged_share": flag.mean()}
        for tname, t in (("negative", neg), ("negative_or_mixed", negmix)):
            p, rc, f1 = prf(flag, t)
            r.update({f"precision_{tname}": p, f"recall_{tname}": rc, f"f1_{tname}": f1})
        ag.append(r)
    ag = pd.DataFrame(ag)
    ag.to_csv(OUT / "v2_cutoff_agreement.csv", index=False, float_format="%.4f")

    # ---- rankings
    dl = pd.read_csv(ROOT / "outputs" / "q1_by_dealer.csv").set_index("dealer_code")
    rk = pd.DataFrame({"dealer": dl["dealer"], "n": dl["n"], "dissatisfied_share": dl["dissatisfied_share"],
                       "rank_dissatisfied": dl["dissatisfied_share"].rank(ascending=False, method="min").astype(int),
                       "at_risk_share": dl["at_risk_share"],
                       "rank_at_risk": dl["at_risk_share"].rank(ascending=False, method="min").astype(int)})
    rk["rank_change"] = rk["rank_dissatisfied"] - rk["rank_at_risk"]
    rk.sort_values("rank_dissatisfied").to_csv(OUT / "v2_rank_comparison.csv", float_format="%.4f")
    dp = pd.read_csv(ROOT / "outputs" / "q1_by_department.csv").set_index("department")
    order = lambda col: " > ".join(dp[col].sort_values(ascending=False).index)
    spearman = rk["dissatisfied_share"].rank().corr(rk["at_risk_share"].rank())
    top5 = lambda col: set(rk.sort_values(col, ascending=False).head(5)["dealer"])
    moved = rk[rk["rank_change"].abs() >= 3]
    print(f"labelled comments with a score: {len(g)} (AI negative {neg.mean():.1%}, negative or mixed {negmix.mean():.1%})")
    print(ag.round(3).to_string(index=False))
    print(f"department order, dissatisfied: {order('dissatisfied_share')} | at risk: {order('at_risk_share')}")
    print(f"dealer rank correlation (Spearman): {spearman:.3f}; same top 5: {top5('dissatisfied_share') == top5('at_risk_share')}; "
          f"dealers moving 3 or more places: {len(moved)} ({', '.join(f'{r.dealer} {r.rank_change:+d}' for r in moved.itertuples())})")
    print("top 5 dissatisfied:", sorted(top5("dissatisfied_share")), "| top 5 at risk:", sorted(top5("at_risk_share")))


if __name__ == "__main__":
    main()
