"""
make_figures.py - report figures from output files only.

outputs/figures/q2_dissatisfied_by_group.png: monthly dissatisfied share for Parramatta, Dandenong and the
other 19 like-for-like dealers combined, from outputs/q2_monthly_by_group.csv, with a vertical line at
5 May 2026 (booking-system go-live, Dandenong 'May 26' tab, cell A3; outputs/derived_numbers.csv).
Points are plotted mid-month. No API calls.   Run after analysis.ipynb:  python make_figures.py
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "outputs" / "q2_monthly_by_group.csv"
OUT = ROOT / "outputs" / "figures" / "q2_dissatisfied_by_group.png"
GO_LIVE = pd.Timestamp("2026-05-05")
STYLE = {"Parramatta": ("#c0392b", "o"), "Dandenong": ("#e67e22", "s"), "other 19 like-for-like": ("#2c3e50", "^")}
LABEL = {"other 19 like-for-like": "Other 19 dealers (combined)"}


def main():
    g = pd.read_csv(SRC)
    assert set(g["group"]) == set(STYLE) and g.groupby("group").size().eq(12).all(), "expected 12 months for each of 3 groups"
    g["date"] = pd.to_datetime(g["month"] + "-15")
    fig, ax = plt.subplots(figsize=(8, 3.6), dpi=200)
    for grp, (colour, marker) in STYLE.items():
        d = g[g["group"] == grp].sort_values("date")
        ax.plot(d["date"], 100 * d["dissatisfied_share"], color=colour, marker=marker, markersize=4, linewidth=1.8,
                label=f"{LABEL.get(grp, grp)} (n per month {d['n'].min()}-{d['n'].max()})")
    ax.axvline(GO_LIVE, color="#7f8c8d", linestyle="--", linewidth=1)
    ax.annotate("Booking system live, 5 May", xy=(GO_LIVE, 0.97), xycoords=("data", "axes fraction"),
                xytext=(4, 0), textcoords="offset points", ha="left", va="top", fontsize=8, color="#555555")
    ax.set_ylabel("Dissatisfied share (%)")
    ax.set_ylim(0, 55)
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b\n%y"))
    ax.tick_params(labelsize=8)
    ax.grid(axis="y", alpha=0.3)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.legend(fontsize=8, frameon=False, loc="upper left")
    ax.set_title("Dissatisfied share by month, Oct 2025 to Sep 2026", fontsize=10, loc="left")
    fig.text(0.01, 0.005, "Source: outputs/q2_monthly_by_group.csv. Dissatisfied = score below 40 of 100.", fontsize=7, color="#777777")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, metadata={"Software": None})
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
