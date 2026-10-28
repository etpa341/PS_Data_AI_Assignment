"""
make_extra_check.py - hand-check sheet for the two themes the 120-row sample never contained.

Vehicle or product and Other had no hand-labelled rows, so 04_evaluate.py could not score them. This samples up
to 20 comments the AI labelled with each as primary theme, from outside the 120 Labels rows and the 30 Voice_check
rows, seed 42. The two groups are shuffled together and exported WITHOUT any AI label (blind check).
The AI labels are recovered later from data/silver_labels/labels.csv by feedback_id.

Refuses to overwrite an existing sheet (it may hold hand labels); pass --force to rebuild. No API calls.
Run:  python make_extra_check.py
"""
import sys
from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.worksheet.datavalidation import DataValidation

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent
import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location("mls", ROOT / "make_labelling_sheet.py")
mls = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mls)

OUT = ROOT / "labelling" / "extra_check.xlsx"
SHEET = ROOT / "labelling" / "labelling_sheet.xlsx"
SEED, N_EACH = 42, 20
CHECK_THEMES = ["Vehicle or product", "Other"]


def main():
    if OUT.exists() and "--force" not in sys.argv:
        sys.exit(f"{OUT} already exists and may hold hand labels. Pass --force to rebuild it.")
    s = pd.read_csv(mls.SILVER, dtype=str, keep_default_na=False)
    lab = pd.read_csv(ROOT / "data" / "silver_labels" / "labels.csv", dtype=str, keep_default_na=False)
    used = set(pd.read_excel(SHEET, sheet_name="Labels", dtype=str)["feedback_id"]) | \
        set(pd.read_excel(SHEET, sheet_name="Voice_check", dtype=str)["feedback_id"])
    pool = lab[(lab["label_status"] == "labelled") & ~lab["feedback_id"].isin(used)].merge(
        s[["feedback_id", "dealer_code", "department", "comment_clean"]], on="feedback_id")

    parts, counts = [], {}
    for t in CHECK_THEMES:
        p = pool[pool["primary_theme"] == t]
        k = min(N_EACH, len(p))
        counts[t] = (k, len(p))
        parts.append(p.sample(k, random_state=SEED))
    sample = pd.concat(parts).sample(frac=1, random_state=SEED).reset_index(drop=True)
    assert sample["feedback_id"].is_unique and not set(sample["feedback_id"]) & used

    wb = Workbook()
    ws = wb.active
    ws.title = "Labels"
    ws.append(["feedback_id", "dealer_code", "department", "comment_clean",
               "my_primary_theme", "my_secondary_theme", "my_sentiment", "notes"])
    for r in sample.itertuples():          # no AI columns
        ws.append([r.feedback_id, r.dealer_code, r.department, r.comment_clean, None, None, None, None])
    last = len(sample) + 1
    dv_theme = DataValidation(type="list", formula1='"' + ",".join(mls.THEMES) + '"', allow_blank=True)
    dv_sent = DataValidation(type="list", formula1='"' + ",".join(mls.SENTIMENTS) + '"', allow_blank=True)
    for dv in (dv_theme, dv_sent):
        dv.error, dv.errorTitle, dv.showErrorMessage = "Pick a value from the list", "Not in list", True
        ws.add_data_validation(dv)
    dv_theme.add(f"E2:F{last}")
    dv_sent.add(f"G2:G{last}")
    mls.style(ws, {"A": 18, "B": 11, "C": 11, "D": 80, "E": 26, "F": 26, "G": 13, "H": 30})

    # the final definitions the 120 rows were labelled with (single source)
    d = pd.read_excel(SHEET, sheet_name="Definitions", dtype=str).fillna("")
    wd = wb.create_sheet("Definitions")
    wd.append(list(d.columns))
    for row in d.itertuples(index=False):
        wd.append(list(row))
    mls.style(wd, {"A": 26, "B": 100, "C": 50})

    wb.save(OUT)
    print(f"wrote {OUT.relative_to(ROOT)}: {len(sample)} rows, shuffled, no AI labels; "
          + "; ".join(f"{t}: {k} of {n} available" for t, (k, n) in counts.items())
          + f" (pool excludes the {len(used)} Labels/Voice_check rows)")


if __name__ == "__main__":
    main()
