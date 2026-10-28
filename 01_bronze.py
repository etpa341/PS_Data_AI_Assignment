"""
01_bronze.py - read every feedback file and sheet as-is.

- Source files are opened read-only and never written.
- Each file is matched to exactly one family in config/file_mappings.yaml, which gives the
  header row(s), delimiter, encoding and the column mapping.
- Every non-blank row is kept and classed (header, banner, data, total, note), so nothing is
  dropped silently. Values are stored as text, exactly as read.
- PII columns marked "drop:" in the config are never written (SPEC section 8). Only a count of
  dropped cells and a one-way row hash (used to find exact duplicate rows) are kept. Staff
  first names are collected into a list before the staff columns are dropped.

Outputs:
  data/bronze/bronze_rows.csv        one row per non-blank source row
  data/bronze/bronze_sheets.csv      one row per file and sheet: counts, status, errors
  data/bronze/staff_names.csv        staff first names from the staff columns (for redaction)
  outputs/bronze_reconciliation.csv  bronze data rows vs profiling Manifest row_count

Run:  python 01_bronze.py
"""
import csv
import fnmatch
import hashlib
import io
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

import openpyxl
import pandas as pd
import yaml
from collections import Counter

ROOT = Path(__file__).resolve().parent
FEEDBACK = ROOT / "feedback"
CONFIG = yaml.safe_load((ROOT / "config" / "file_mappings.yaml").read_text(encoding="utf-8"))
GOVERNANCE = ROOT / "profiling" / "data_governance.xlsx"
BRONZE = ROOT / "data" / "bronze"
OUTPUTS = ROOT / "outputs"
DEFAULTS = CONFIG["defaults"]
TOTAL_RE = re.compile(DEFAULTS["total_row_regex"], re.I)
STAFF_VALUES = Counter()   # (family, raw staff cell) -> rows; source for the staff first-name list
FIELDS = ["date_raw", "department_raw", "rating_raw", "comment_raw", "site_raw",
          "vehicle_raw", "action_raw", "channel_raw", "month_raw"]


def as_text(v):
    """Cell value -> text, without reinterpreting it."""
    if v is None:
        return ""
    if isinstance(v, datetime):
        return v.isoformat(sep=" ")
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def family_for(fname):
    hits = [f for f in CONFIG["families"] if any(fnmatch.fnmatch(fname, p) for p in f["files"])]
    if len(hits) != 1:
        raise ValueError(f"{fname}: matched {len(hits)} families in config (need exactly 1)")
    return hits[0]


def sheet_config(fam, fname, sheet):
    cfg = {"header_rows": fam.get("header_rows", DEFAULTS["header_rows"])}
    cfg.update(fam.get("sheets", {}).get(sheet, {}))
    cfg.update(fam.get("sheets_by_file", {}).get(fname, {}).get(sheet, {}))
    return cfg


def read_csv(path, fam):
    enc = fam.get("encoding", DEFAULTS["encoding"])
    text = path.read_bytes().decode(enc)            # strict: fails loudly on the wrong encoding
    delim = fam.get("delimiter", DEFAULTS["delimiter"])
    return [("(csv)", list(csv.reader(io.StringIO(text), delimiter=delim)), "visible")]


def read_xlsx(path):
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    out = [(ws.title, [list(r) for r in ws.iter_rows(values_only=True)], ws.sheet_state) for ws in wb.worksheets]
    wb.close()
    return out


def bronze_sheet(fname, sheet, rows, fam):
    """Class every row of one sheet and map columns. Returns (records, sheet_summary)."""
    cfg = sheet_config(fam, fname, sheet)
    rows = [[as_text(v).strip() if isinstance(v, str) else as_text(v) for v in r] for r in rows]
    summary = {"source_file": fname, "source_sheet": sheet, "family": fam["family"], "raw_rows": len(rows),
               "header_rows": "", "banner": 0, "blank": 0, "header": 0, "data": 0, "total": 0, "note": 0,
               "pii_cells_dropped": 0, "status": "ok", "error": ""}
    if cfg.get("empty"):
        nonblank = sum(any(v for v in r) for r in rows)
        if nonblank:
            raise ValueError(f"{fname} [{sheet}] is configured as empty but has {nonblank} non-blank rows")
        summary["status"] = "empty sheet (config)"
        return [], summary

    hdr_rows = cfg["header_rows"]
    summary["header_rows"] = ", ".join(map(str, hdr_rows))
    colmap = fam["columns"]
    recs = []

    def base(i, cls, block):
        return {"source_file": fname, "source_sheet": sheet, "source_row": i + 1, "family": fam["family"],
                "block": block, "row_class": cls}

    for i in range(hdr_rows[0] - 1):                 # banner rows above the first header
        if any(rows[i]):
            recs.append({**base(i, "banner", 0), "note_text": " | ".join(v for v in rows[i] if v)})
            summary["banner"] += 1
        else:
            summary["blank"] += 1

    for b, h in enumerate(hdr_rows):
        header = rows[h - 1]
        unknown = [c for c in header if c and c not in colmap]
        if unknown:
            raise ValueError(f"{fname} [{sheet}] row {h}: header cells not in config: {unknown}")
        if not any(header):
            raise ValueError(f"{fname} [{sheet}] row {h}: configured header row is blank")
        recs.append({**base(h - 1, "header", b + 1), "note_text": " | ".join(c for c in header if c)})
        summary["header"] += 1
        date_col = next((k for k, c in enumerate(header) if colmap.get(c) == "date_raw"), None)
        end = hdr_rows[b + 1] - 1 if b + 1 < len(hdr_rows) else len(rows)
        for i in range(h, end):
            r = rows[i]
            ne = [v for v in r if v]
            if not ne:
                summary["blank"] += 1
                continue
            # values in columns without a header would be silently lost: stop instead
            orphan = [k + 1 for k, v in enumerate(r) if v and (k >= len(header) or not header[k])]
            if orphan:
                raise ValueError(f"{fname} [{sheet}] row {i + 1}: data in unnamed column(s) {orphan}")
            date_val = r[date_col] if date_col is not None and date_col < len(r) else ""
            if TOTAL_RE.match(ne[0].lower()):
                cls = "total"
            elif len(ne) == 1 and len(ne[0]) > 15 and not re.match(r"\d", date_val or "x"):
                cls = "note"                          # single long text cell, no date (e.g. footer)
            else:
                cls = "data"
            rec = base(i, cls, b + 1)
            rec["raw_row_hash"] = hashlib.sha256("\x1f".join(r).encode("utf-8")).hexdigest()[:16]
            counts = {}
            for k, c in enumerate(header):
                if not c or k >= len(r):
                    continue
                target, v = colmap[c], r[k]
                if target.startswith("drop:"):
                    summary["pii_cells_dropped"] += bool(v)
                    if target == "drop:staff" and v and cls == "data":
                        STAFF_VALUES[(fam["family"], v)] += 1
                elif target.startswith("count_raw:"):
                    counts[target.split(":", 1)[1]] = v
                else:
                    if target == "rating_raw":
                        rec["rating_column"] = c
                    if v:
                        rec[target] = v
            if counts:
                rec["counts_raw"] = json.dumps(counts)
            if cls != "data":
                rec["note_text"] = " | ".join(str(rec.get(f, "")) for f in FIELDS if rec.get(f))
                for f in FIELDS:
                    rec.pop(f, None)
            recs.append(rec)
            summary[cls] += 1
    data = [r for r in recs if r["row_class"] == "data"]
    summary["sheet_content_hash"] = hashlib.sha256(
        "\n".join(r["raw_row_hash"] for r in data).encode()).hexdigest()[:16] if data else ""
    return recs, summary


def main():
    BRONZE.mkdir(parents=True, exist_ok=True)
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    all_recs, sheets = [], []
    files = sorted(p for p in FEEDBACK.iterdir() if p.is_file())
    for path in files:
        if path.name.startswith("~$"):
            sheets.append({"source_file": path.name, "source_sheet": "", "status": "skipped: Excel lock file (not data)"})
            continue
        try:
            fam = family_for(path.name)
            loaded = read_csv(path, fam) if fam["format"] == "csv" else read_xlsx(path)
            for sheet, rows, state in loaded:
                recs, summ = bronze_sheet(path.name, sheet, rows, fam)
                summ["sheet_state"] = state
                all_recs += recs
                sheets.append(summ)
        except Exception as e:                       # recorded, never skipped silently
            sheets.append({"source_file": path.name, "source_sheet": "", "status": "ERROR", "error": f"{type(e).__name__}: {e}"})

    cols = ["source_file", "source_sheet", "source_row", "family", "block", "row_class", *FIELDS,
            "rating_column", "counts_raw", "note_text", "raw_row_hash"]
    rows_df = pd.DataFrame(all_recs).reindex(columns=cols)
    rows_df.to_csv(BRONZE / "bronze_rows.csv", index=False, encoding="utf-8")
    sheets_df = pd.DataFrame(sheets)
    sheets_df.to_csv(BRONZE / "bronze_sheets.csv", index=False, encoding="utf-8")

    # staff first names, taken from the staff columns before they are dropped (used by silver to
    # redact staff names in comment text); first capitalised token of each cell
    names = {}
    for (family, v), k in STAFF_VALUES.items():
        m = re.match(r"[A-Z][a-z]+", v.strip())
        if m:
            e = names.setdefault(m.group(0), {"families": set(), "rows": 0})
            e["families"].add(family)
            e["rows"] += k
    pd.DataFrame([{"first_name": n, "families": "; ".join(sorted(e["families"])), "rows": e["rows"]}
                  for n, e in sorted(names.items())]).to_csv(BRONZE / "staff_names.csv", index=False)

    # ---- reconcile with the profiling Manifest ----
    man = pd.read_excel(GOVERNANCE, sheet_name="Manifest")
    man = man[~man["file_name"].astype(str).str.startswith("~$")]
    man = man[~man["sheet_kind"].astype(str).str.startswith("NOT DATA")]
    m = man[["file_name", "sheet_name", "row_count"]].rename(
        columns={"file_name": "source_file", "sheet_name": "source_sheet", "row_count": "manifest_rows"})
    b = sheets_df[sheets_df["status"].isin(["ok", "empty sheet (config)"])][["source_file", "source_sheet", "data"]]
    b = b.rename(columns={"data": "bronze_data_rows"})
    rec = m.merge(b, on=["source_file", "source_sheet"], how="outer", indicator=True)
    rec["match"] = (rec["_merge"] == "both") & (rec["manifest_rows"].fillna(-1) == rec["bronze_data_rows"].fillna(-2))
    rec = rec.drop(columns="_merge")
    rec.to_csv(OUTPUTS / "bronze_reconciliation.csv", index=False)

    n_files = sum(1 for p in files if not p.name.startswith("~$"))
    checks = {
        "52 data files found": n_files == 52,
        "no file errors": not (sheets_df["status"] == "ERROR").any(),
        "every file/sheet in Manifest is in bronze and counts match": bool(rec["match"].all()),
        "bronze data rows total == Manifest total": int(rows_df["row_class"].eq("data").sum()) == int(m["manifest_rows"].sum()),
        "no PII column names in bronze output": not any(c in rows_df.columns for c in ("customer_name", "phone", "email", "rego", "customer_id")),
    }
    print(f"files: {n_files}  sheets: {len(sheets_df)}  bronze rows: {len(rows_df)}  "
          f"data rows: {int(rows_df['row_class'].eq('data').sum())}  manifest rows: {int(m['manifest_rows'].sum())}")
    print(rows_df["row_class"].value_counts().to_string())
    for k, v in checks.items():
        print(f"  [{'PASS' if v else 'FAIL'}] {k}")
    if not all(checks.values()):
        print(rec[~rec["match"]].to_string())
        print(sheets_df[sheets_df["status"] == "ERROR"][["source_file", "error"]].to_string())
        sys.exit(1)


if __name__ == "__main__":
    main()
