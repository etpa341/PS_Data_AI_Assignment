"""
02_silver.py - one trusted feedback table from bronze.

Steps, in order:
  1. dealer_code      from config (fixed per family, or Site column for North QLD)
  2. dates            per-file format (D/M, M/D, ISO, Excel, d-Mon-yy); D4 Shepparton year fix;
                      Ipswich vague dates -> month only
  3. ratings          D1: true scale min/max, Geelong 2025 inversion fixed first, score_norm 0-100,
                      dissatisfied (< 40) and at_risk (<= 50)
  4. department       shared vocabulary; Essendon from tab; Bendigo codes (D3, inferred)
  5. comments         redact phone / email / plate / name prefix; has_text; voice
  6. exclusions       whole sheets from config (each re-checked against the data), test rows,
                      exact duplicates, Essendon cross-tab copies, dates outside the window.
                      Excluded rows stay in the table with excluded = true and exclude_reason.
  7. validation       every rule logs rows checked, rows failed and the action taken

Outputs:
  data/silver/feedback_silver.csv
  outputs/dq_rule_log.csv        rule, rows checked, rows failed, action
  outputs/exclusions.csv         every excluded row group with its reason
  outputs/quality_report.md      the two tables above plus reconciliation, as a readable report

No LLM or network calls. Run after 01_bronze.py:  python 02_silver.py
"""
import hashlib
import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent
CONFIG = yaml.safe_load((ROOT / "config" / "file_mappings.yaml").read_text(encoding="utf-8"))
BRONZE = ROOT / "data" / "bronze"
SILVER = ROOT / "data" / "silver"
OUTPUTS = ROOT / "outputs"
WINDOW_START, WINDOW_END = date(2025, 10, 1), date(2026, 9, 30)
FAMILIES = {f["family"]: f for f in CONFIG["families"]}
SCALES = CONFIG["scales"]
MON = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}

SILVER_COLUMNS = ["feedback_id", "source_file", "source_sheet", "source_row", "dealer_code", "department",
                  "date_raw", "feedback_date", "date_corrected", "month", "rating_raw", "rating_scale",
                  "score_norm", "dissatisfied", "at_risk", "comment_clean", "has_text", "voice",
                  "dept_inferred", "dq_flags", "excluded", "exclude_reason"]

# PII patterns (same as profiling, plus case-insensitive 'rego' and capitals inside surnames)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
PHONE_RE = re.compile(r"(?<!\d)(?:\+?61\s?|0)[2-478](?:[ -]?\d){8}(?!\d)")
REGO_WORD_RE = re.compile(r"((?i:\brego)\s*:?\s*)[A-Z0-9]{5,7}\b")
PLATE_RE = re.compile(r"\b(?=[A-Z0-9]*\d)(?=[A-Z0-9]*[A-Z])[A-Z0-9]{6}\b")
NAME_PREFIX_RE = re.compile(r"^[A-Z][a-z]+ [A-Z][A-Za-z'\-]+ - ")
# third-person staff write-ups ("Cust said ...", "Said the crew ...", "Complained the ...")
PARAPHRASE_RE = re.compile(
    r"^(?:\[NAME\] - )?(?:cust\b|said\b|reckoned\b|complained\b|sarcastic\s+-|older (?:lady|gent|bloke)\b)"
    r"|\bsaid (?:he|she)\b|\b(?:he|she) said\b"
    r"|\b(?:cust|customer)\s+(?:said|says|reckons|was|is|felt|thinks|thought|wants|wanted|unhappy|happy|"
    r"complained|rang|called|wrote|mentioned|asked|stated|noted)\b", re.I)
# a write-up in the customer's own words uses the first person; staff paraphrases do not
FIRST_PERSON_RE = re.compile(r"\b(?:I|I'm|I've|I'd|I'll)\b|\b(?:me|my|myself|mine)\b", re.I)
# cues that only a staff member writes, even when the comment quotes the customer ("I ...")
STAFF_CUE_RE = re.compile(r"\bcust\b|\bsaid (?:cust|customer)\b", re.I)
POS_KW = re.compile(r"\b(?:great|excellent|friendly|helpful|thank|thanks|cheers|fantastic|lovely|happy|recommend|ace|legend|impressed|pleased|smooth|well done|top notch)\b", re.I)
NEG_KW = re.compile(r"\b(?:rude|never|waited|disappoint\w*|useless|terrible|worst|nobody|no one|overcharg\w*|chas\w+|complain\w*|annoy\w*|unhappy|not happy|ridiculous|appalling|still)\b", re.I)

rules = []      # rule log: one dict per rule


def log(rule_id, rule, checked, failed, action, detail=""):
    rules.append({"rule_id": rule_id, "rule": rule, "rows_checked": int(checked), "rows_failed": int(failed),
                  "action": action, "detail": detail})


# --------------------------------------------------------------------------------------
# Dates
# --------------------------------------------------------------------------------------
def slash_parts(s):
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{2}|\d{4})", s)
    if not m:
        return None
    a, b, y = m.groups()
    return int(a), int(b), int(y) + (2000 if len(y) == 2 else 0)


def parse_date(s, fmt):
    """Return a date or None. ISO text (from Excel datetime cells) is accepted for every format."""
    s = s.strip()
    if not s or fmt == "none":
        return None
    if m := re.match(r"(\d{4})-(\d{2})-(\d{2})", s):
        return date(*map(int, m.groups()))
    try:
        if fmt == "excel" and re.fullmatch(r"\d{5}(\.\d+)?", s):
            return (datetime(1899, 12, 30) + timedelta(days=float(s))).date()
        if fmt in ("dmy", "dmy_2y", "mdy") and (p := slash_parts(s)):
            a, b, y = p
            return date(y, a, b) if fmt == "mdy" else date(y, b, a)
        if fmt == "d_mon_yy" and (m := re.fullmatch(r"(\d{1,2})[- ]([A-Za-z]{3})[- ](\d{2}|\d{4})", s)):
            d, mon, y = m.groups()
            return date(int(y) + (2000 if len(y) == 2 else 0), MON[mon.lower()], int(d))
    except (ValueError, KeyError):
        return None
    return None


def vague_month(s):
    """'early Oct', 'wk1 Feb', 'Aug?' -> month number, else None."""
    m = re.fullmatch(r"(?:(?:early|mid|late|wk\d)\s*)?([A-Za-z]{3})\??", s.strip(), re.I)
    return MON.get(m.group(1).lower()) if m else None


def period_months(fname, sheet):
    """Months implied by the sheet name, else the file name, else None (= whole window)."""
    def from_text(t):
        t = t.lower()
        if "2025-26" in t or "25-26" in t:
            return None
        if m := re.search(r"(20\d\d)[\s_]*q([1-4])|q([1-4])[\s_]*(20\d\d)", t):
            y, q = int(m.group(1) or m.group(4)), int(m.group(2) or m.group(3))
            start = pd.Period(f"{y}-{3 * q - 2:02d}", "M")
            return {str(start + k) for k in range(3)}
        if m := re.search(r"(20\d\d)-(\d{2})(?!\d)", t):
            if 1 <= int(m.group(2)) <= 12:
                return {f"{m.group(1)}-{m.group(2)}"}
        if m := re.search(r"([a-z]{3})(\d{2})-([a-z]{3})(\d{2})", t):
            a = pd.Period(f"20{m.group(2)}-{MON[m.group(1)]:02d}", "M")
            b = pd.Period(f"20{m.group(4)}-{MON[m.group(3)]:02d}", "M")
            return {str(p) for p in pd.period_range(a, b, freq="M")}
        if m := re.fullmatch(r"([a-z]{3}) (\d{2})", t.strip()):
            return {f"20{m.group(2)}-{MON[m.group(1)]:02d}"}
        if m := re.fullmatch(r"(20\d\d)", t.strip()):
            return {str(p) for p in pd.period_range(WINDOW_START, WINDOW_END, freq="M") if p.year == int(m.group(1))}
        return None
    return from_text(sheet) if sheet != "(csv)" and from_text(sheet) else from_text(Path(fname).stem)


# --------------------------------------------------------------------------------------
# Ratings
# --------------------------------------------------------------------------------------
def rating_value(raw, scale):
    """Raw rating text -> number on the scale, or (None, reason)."""
    s = raw.strip()
    if not s:
        return None, "rating_missing"
    if scale["kind"] == "numeric":
        try:
            x = float(s)
        except ValueError:
            return None, "rating_unparseable"
        if not x.is_integer() or not scale["min"] <= x <= scale["max"]:
            return None, "rating_out_of_scale"
        return x, ""
    if scale["kind"] == "labels":
        x = scale["map"].get(s.lower())
        return (float(x), "") if x else (None, "rating_unparseable")
    if scale["kind"] == "stars":
        if len(s) != scale["max"] or set(s) - {"★", "☆"}:
            return None, "rating_unparseable"
        return float(s.count("★")), ""
    raise ValueError(scale)


# --------------------------------------------------------------------------------------
# Comments
# --------------------------------------------------------------------------------------
def redact(text):
    """Return (clean_text, list_of_pattern_names_hit)."""
    hits = []
    for name, rx, repl in (("email", EMAIL_RE, "[EMAIL]"), ("phone", PHONE_RE, "[PHONE]"),
                           ("rego", REGO_WORD_RE, r"\1[REGO]"), ("plate", PLATE_RE, "[REGO]"),
                           ("name_prefix", NAME_PREFIX_RE, "[NAME] - ")):
        text, n = rx.subn(repl, text)
        if n:
            hits.append(name)
    return text, hits


UNLISTED_STAFF_HASHES = set(yaml.safe_load((ROOT / "config" / "redaction.yaml").read_text(encoding="utf-8"))
                            ["unlisted_staff_name_sha256_16"])
WORD_RE = re.compile(r"\b[A-Za-z]+\b")


def name_hash(word):
    return hashlib.sha256(word.lower().encode("utf-8")).hexdigest()[:16]


def redact_staff(text, staff_re):
    """Replace listed (regex, any case) and unlisted (hashed) staff first names with [STAFF].
    Returns (text, listed names found, number of unlisted names replaced)."""
    found = staff_re.findall(text)
    text = staff_re.sub("[STAFF]", text)
    n = 0

    def sub(m):
        nonlocal n
        if name_hash(m.group(0)) in UNLISTED_STAFF_HASHES:
            n += 1
            return "[STAFF]"
        return m.group(0)
    return WORD_RE.sub(sub, text), found, n


def staff_name_tokens_left(text, staff):
    """Check, independent of redact_staff: split into letter runs character by character (no regex) and
    compare each lower-cased token with the listed names and the unlisted-name hashes."""
    listed = {s.lower() for s in staff}
    tokens = "".join(ch.lower() if ch.isalpha() else " " for ch in text).split()
    return any(t in listed or name_hash(t) in UNLISTED_STAFF_HASHES for t in tokens)


def pii_left(text):
    return bool(EMAIL_RE.search(text) or PHONE_RE.search(text) or PLATE_RE.search(text.replace("[REGO]", ""))
                or NAME_PREFIX_RE.search(text) or re.search(r"(?i:\brego)\s*:?\s*(?!\[REGO\])[A-Z0-9]{5,7}\b", text))


# --------------------------------------------------------------------------------------
def main():
    SILVER.mkdir(parents=True, exist_ok=True)
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    bronze = pd.read_csv(BRONZE / "bronze_rows.csv", dtype=str, keep_default_na=False)
    sheets = pd.read_csv(BRONZE / "bronze_sheets.csv", dtype=str, keep_default_na=False)
    dealers = pd.read_csv(ROOT / "reference" / "dealerships.csv")
    closed = {r.dealer_code: date.fromisoformat(r.closed_date) for r in dealers.itertuples() if isinstance(r.closed_date, str)}
    df = bronze[bronze["row_class"] == "data"].copy().reset_index(drop=True)
    df["source_row"] = df["source_row"].astype(int)
    n = len(df)
    flags = [[] for _ in range(n)]
    reasons = [[] for _ in range(n)]
    fam = df["family"].map(FAMILIES)

    def flag(mask, name):
        for i in df.index[mask]:
            flags[i].append(name)

    def exclude(mask, reason):
        for i in df.index[mask]:
            reasons[i].append(reason)

    # ---- 1. dealer_code ------------------------------------------------------------
    site_alias = CONFIG["site_aliases"]
    df["dealer_code"] = [site_alias.get(s.strip().lower(), "UNMAPPED_SITE") if f.get("dealer_from_site") else f["dealer_code"]
                         for f, s in zip(fam, df["site_raw"])]
    known = set(dealers["dealer_code"])
    bad = ~df["dealer_code"].isin(known)
    log("R01", "Dealer code exists in dealerships.csv", n, bad.sum(), "ask" if bad.any() else "none needed",
        "North QLD rows mapped from the Site column via site_aliases")
    alias = fam.map(lambda f: bool(f.get("dealer_alias")))
    flag(alias, "dealer_alias")
    log("R02", "Dealer mapped by alias, not by suburb name (Hunter -> NSW05, IPS -> QLD03)", n, alias.sum(), "flag",
        "Suspected mappings from profiling (brand mix supports Hunter); confirm with head office")

    # ---- 2. dates --------------------------------------------------------------------
    def fmt_for(f, fname):
        return f.get("date_format_by_file", {}).get(fname, f["date_format"])

    df["_fmt"] = [fmt_for(f, fn) for f, fn in zip(fam, df["source_file"])]
    parsed = [parse_date(s, fmt) for s, fmt in zip(df["date_raw"], df["_fmt"])]
    df["feedback_date"] = parsed
    has_date_fmt = df["_fmt"] != "none"

    # date order evidence per file: D/M files must have no 2nd part > 12, M/D files no 1st part > 12
    order_fail = []
    for (fname, fmt), g in df[df["_fmt"].isin(["dmy", "dmy_2y", "mdy"])].groupby(["source_file", "_fmt"]):
        parts = [p for p in map(slash_parts, g["date_raw"]) if p]
        wrong = sum((p[1] > 12) if fmt != "mdy" else (p[0] > 12) for p in parts)
        proof = sum((p[0] > 12) if fmt != "mdy" else (p[1] > 12) for p in parts)
        if wrong or not proof:
            order_fail.append(f"{fname}: {wrong} contradicting, {proof} proving")
    slash_rows = df["_fmt"].isin(["dmy", "dmy_2y", "mdy"]).sum()
    log("R03", "Day/month order proven per file (D/M files: no 2nd part > 12; M/D files: no 1st part > 12)",
        slash_rows, len(order_fail), "fix (parse liverpool_q3_2026.csv as M/D)",
        "; ".join(order_fail) or "every slash-date file has proving values and none contradicting")

    # Ipswich vague dates -> month only (each calendar month occurs once in the window)
    df["month"] = [d.strftime("%Y-%m") if d else "" for d in df["feedback_date"]]
    vague_mask = pd.Series(False, index=df.index)
    for i in df.index[df["feedback_date"].isna() & has_date_fmt]:
        if fam[i].get("vague_dates") == "infer_month" and (m := vague_month(df.at[i, "date_raw"])):
            y = 2025 if m >= 10 else 2026
            df.at[i, "month"] = f"{y}-{m:02d}"
            vague_mask[i] = True
    # neighbour sanity check: inferred month within 1 month of the nearest parsed rows in file order
    vague_bad = 0
    for i in df.index[vague_mask]:
        g = df[(df["source_file"] == df.at[i, "source_file"]) & df["feedback_date"].notna()]
        prev = g[g["source_row"] < df.at[i, "source_row"]].tail(1)
        nxt = g[g["source_row"] > df.at[i, "source_row"]].head(1)
        p = pd.Period(df.at[i, "month"], "M")
        near = [abs((pd.Period(d.strftime("%Y-%m"), "M") - p).n) for d in list(prev["feedback_date"]) + list(nxt["feedback_date"])]
        if not near or min(near) > 1:
            vague_bad += 1
    flag(vague_mask, "date_vague_month_inferred")
    unparsed = df["feedback_date"].isna() & has_date_fmt
    flag(unparsed & ~vague_mask, "date_unparsed")
    log("R04", "Date parses with the file's format", has_date_fmt.sum(), unparsed.sum(),
        "flag; month inferred for vague dates",
        f"{vague_mask.sum()} vague Ipswich dates ('early Oct', 'Aug?') -> month only, feedback_date left empty; "
        f"{vague_bad} of them fail the neighbour check; {(unparsed & ~vague_mask).sum()} others unparsed (test rows)")

    # D4 Shepparton: dates after closure moved back one year when row order supports it
    df["date_corrected"] = False
    after_close = pd.Series([bool(d and dc in closed and d > closed[dc]) for d, dc in zip(df["feedback_date"], df["dealer_code"])])
    fixed, not_fixed = 0, 0
    for i in df.index[after_close]:
        d = df.at[i, "feedback_date"]
        cand = d.replace(year=d.year - 1)
        g = df[(df["source_file"] == df.at[i, "source_file"]) & df["feedback_date"].notna() & ~after_close]
        prev = g[g["source_row"] < df.at[i, "source_row"]].tail(1)["feedback_date"].tolist()
        nxt = g[g["source_row"] > df.at[i, "source_row"]].head(1)["feedback_date"].tolist()
        fits = any(abs((cand - x).days) <= 31 for x in prev + nxt)
        dc = df.at[i, "dealer_code"]
        if FAMILIES[df.at[i, "family"]].get("year_correction") == "after_closure" and WINDOW_START <= cand <= closed[dc] and fits:
            df.at[i, "feedback_date"] = cand
            df.at[i, "month"] = cand.strftime("%Y-%m")
            df.at[i, "date_corrected"] = True
            fixed += 1
        else:
            not_fixed += 1
    flag(df["date_corrected"], "date_year_corrected")
    vic09 = df["dealer_code"].isin(closed.keys())
    log("R05", "D4: closed-site rows dated after closure (Shepparton, closed 2026-03-31)", vic09.sum(), after_close.sum(),
        "fix (year - 1, date_corrected = true)",
        f"{fixed} corrected (each within 31 days of a file-order neighbour), {not_fixed} left uncorrected")

    fd = df["feedback_date"]
    out_window = fd.notna() & ((fd < WINDOW_START) | (fd > WINDOW_END))
    still_closed = pd.Series([bool(d and dc in closed and d > closed[dc]) for d, dc in zip(fd, df["dealer_code"])])

    periods = {(f, s): period_months(f, s) for f, s in df[["source_file", "source_sheet"]].drop_duplicates().itertuples(index=False)}
    out_period = pd.Series([bool(m and periods[(f, s)] and m not in periods[(f, s)])
                            for f, s, m in zip(df["source_file"], df["source_sheet"], df["month"])])
    flag(out_period, "date_outside_file_period")
    per_sheet = df[out_period].groupby(["source_file", "source_sheet"]).size()
    log("R06", "Row month inside the period named in the file or tab", (df["month"] != "").sum(), out_period.sum(),
        "flag (month always comes from the row date, never the tab name)",
        "; ".join(f"{f} [{s}]: {k}" for (f, s), k in per_sheet.items()) or "none")

    # ---- 3. ratings (D1) -----------------------------------------------------------------
    scale_name = [f.get("rating_scale_by_column", {}).get(col, f["rating_scale"]) for f, col in zip(fam, df["rating_column"])]
    df["rating_scale"] = scale_name
    agg = fam.map(lambda f: f.get("kind") == "aggregate")
    vals, why = zip(*[(None, "aggregate") if a else rating_value(r, SCALES[s]) for r, s, a in zip(df["rating_raw"], scale_name, agg)])
    x = pd.Series(vals, dtype="float")
    x_raw = x.copy()                                           # as recorded, before the inversion fix
    why = pd.Series(why)
    inv = pd.Series([df.at[i, "source_sheet"] in fam[i].get("invert_sheets", []) for i in df.index])
    lo = pd.Series([SCALES[s]["min"] for s in scale_name], dtype="float")
    hi = pd.Series([SCALES[s]["max"] for s in scale_name], dtype="float")
    raw_score = (x - lo) / (hi - lo) * 100                     # before the inversion fix (for R10)
    x = x.where(~inv, lo + hi - x)                             # Geelong 2025: 1 = Excellent -> 6 - x
    df["score_norm"] = ((x - lo) / (hi - lo) * 100).round(1)
    df["dissatisfied"] = (df["score_norm"] < 40).where(df["score_norm"].notna())
    df["at_risk"] = (df["score_norm"] <= 50).where(df["score_norm"].notna())
    flag(inv, "rating_inverted_fixed")
    for reason in ("rating_missing", "rating_out_of_scale", "rating_unparseable"):
        flag(why == reason, reason)
    rated = ~agg
    log("R07", "Rating within the file's true scale", rated.sum(), why.isin(["rating_out_of_scale", "rating_unparseable"]).sum(),
        "flag; score left empty", "scales: " + "; ".join(f"{k}: {v}" for k, v in pd.Series(scale_name)[rated].value_counts().items()))
    log("R08", "Rating present", rated.sum(), (why == "rating_missing").sum(), "flag (row kept for text, no score)",
        "; ".join(f"{f}: {k}" for f, k in df[why == "rating_missing"].groupby("source_file").size().items()))
    log("R09", "D1: Geelong 2025 inverted scale fixed before normalising (x -> 6 - x)", (df["source_file"] == "Geelong Feedback.xlsx").sum(),
        inv.sum(), "fix", "tab 2025 banner: 'Rating: 1 = Excellent, 5 = Poor'")

    # ---- 5. comments (before the sentiment check, which uses the clean text) -------------
    clean, hits = zip(*[redact(t) for t in df["comment_raw"]])
    # staff first names, whole words, ANY letter case (an all-lowercase comment writes the name in lower case):
    #   listed   - built by 01_bronze.py from the staff columns, matched with a regex
    #   unlisted - reviewed names not in any staff column, held only as hashes (config/redaction.yaml)
    staff = pd.read_csv(BRONZE / "staff_names.csv")["first_name"].tolist()
    staff_re = re.compile(r"\b(?:" + "|".join(map(re.escape, sorted(staff, key=len, reverse=True))) + r")\b", re.I)
    clean, found, unlisted_n = zip(*[redact_staff(c, staff_re) for c in clean])
    found, unlisted_n = pd.Series(found), pd.Series(unlisted_n)
    df["comment_clean"] = [c.strip() for c in clean]
    df["has_text"] = df["comment_clean"].str.contains(r"[A-Za-z]", regex=True)
    hits = pd.Series(hits)
    pii_rows = hits.map(bool)
    flag(pii_rows, "pii_redacted")
    left = df["comment_clean"].map(pii_left)
    by_pat = {p: int(hits.map(lambda h: p in h).sum()) for p in ("email", "phone", "rego", "plate", "name_prefix")}
    log("R11", "Personal data patterns in comment text (phone, email, rego/plate, 'Firstname Lastname - ')",
        df["has_text"].sum(), pii_rows.sum(), "fix (redacted in comment_clean)",
        f"rows by pattern: {by_pat}; rows still matching after redaction: {int(left.sum())}")
    staff_rows = found.map(bool) | (unlisted_n > 0)
    flag(staff_rows, "staff_name_redacted")
    staff_counts = found.explode().dropna().str.title().value_counts()
    lower_rows = found.map(lambda f: any(w != w.title() for w in f))
    # independent check: a token-by-token comparison (no regex), not the redaction pattern
    staff_left = df["comment_clean"].map(lambda c: staff_name_tokens_left(c, staff))
    log("R11b", "Staff first names in comment text (staff-column list + reviewed unlisted names, whole word, any case)",
        df["has_text"].sum(), staff_rows.sum(), "fix (replaced with [STAFF] in comment_clean)",
        f"{len(staff)} listed names, {len(staff_counts)} found in comments ({int(staff_counts.sum())} replacements; names not logged)"
        + f"; rows with a listed name not in title case: {int(lower_rows.sum())}"
        + f"; {len(UNLISTED_STAFF_HASHES)} unlisted names (hashed, config/redaction.yaml) in {int((unlisted_n > 0).sum())} rows"
        + f"; rows still holding a staff name after redaction (token-by-token check): {int(staff_left.sum())}. "
        "Best effort: names of staff at dealers without a staff column are only caught if reviewed into config/redaction.yaml")
    pii_cells = sheets["pii_cells_dropped"].replace("", "0").astype(int).sum()
    log("R12", "PII columns (name, phone, email, rego, customer no, record ids, staff) not carried forward",
        len(sheets), 0, "fix (dropped at bronze, never written)", f"{pii_cells} non-empty PII cells dropped at read time")

    para = df["has_text"] & (df["comment_clean"].str.contains(STAFF_CUE_RE)
                             | (df["comment_clean"].str.contains(PARAPHRASE_RE)
                                & ~df["comment_clean"].str.contains(FIRST_PERSON_RE)))
    df["voice"] = ["unknown" if not t else ("staff_paraphrased" if p else f.get("voice_default", CONFIG["defaults"]["voice_default"]))
                   for t, p, f in zip(df["has_text"], para, fam)]
    flag(para, "staff_paraphrase")
    log("R13", "Voice: staff third-person paraphrase vs customer words (regex heuristic)", df["has_text"].sum(), para.sum(),
        "flag (voice = staff_paraphrased; themes use customer voice only)",
        "; ".join(f"{f}: {k}" for f, k in df[para].groupby("source_file").size().items()))

    # ---- 4. department -------------------------------------------------------------------
    dept, inferred = [], []
    for f, sheet, raw in zip(fam, df["source_sheet"], df["department_raw"]):
        v = (sheet if f.get("department_from") == "sheet_name" else raw).strip().lower()
        o = f.get("department_map_override", {}).get(v)
        if o:
            dept.append(o["value"]); inferred.append(bool(o.get("inferred")))
        else:
            dept.append(CONFIG["department_map"].get(v, "Unknown")); inferred.append(False)
    df["department"], df["dept_inferred"] = dept, inferred
    flag(df["dept_inferred"], "dept_inferred")
    unk = (df["department"] == "Unknown") & ~agg
    flag(unk, "dept_unknown")
    log("R14", "Department maps to Sales, Service, Parts (else Unknown)", (~agg).sum(), unk.sum(), "flag",
        f"Unknown raw values: {df.loc[unk, 'department_raw'].replace('', '<blank>').value_counts().to_dict()}; "
        f"{int(df['dept_inferred'].sum())} Bendigo 'S' rows -> Sales, dept_inferred = true (D3)")

    # ---- 6. exclusions ---------------------------------------------------------------------
    keys = df["date_raw"] + "\x1f" + df["rating_raw"] + "\x1f" + df["comment_raw"]
    for ex in CONFIG["exclusions"]:
        m = (df["source_file"] == ex["file"]) & ((df["source_sheet"] == ex["sheet"]) if ex["sheet"] != "*" else True)
        chk, ok, ev = ex["check"], False, ""
        if "subset_of" in chk:
            t = chk["subset_of"]
            other = set(keys[(df["source_file"] == t["file"]) & (df["source_sheet"] == t["sheet"])])
            miss = (~keys[m].isin(other)).sum()
            ok, ev = miss == 0 and len(other) > m.sum(), f"{m.sum()} rows, {miss} not found in {t['file']} ({len(other)} rows)"
        elif "identical_to" in chk:
            t = chk["identical_to"]
            h = sheets.set_index(["source_file", "source_sheet"])["sheet_content_hash"]
            ok, ev = h[(ex["file"], ex["sheet"])] == h[(t["file"], t["sheet"])], f"content hash equal to [{t['sheet']}]"
        elif "header_contains" in chk:
            hdr = bronze[(bronze["source_file"] == ex["file"]) & (bronze["source_sheet"] == ex["sheet"]) & (bronze["row_class"] == "header")]
            ok, ev = hdr["note_text"].str.contains(chk["header_contains"]).any(), f"header: {hdr['note_text'].iloc[0]}"
        elif "kind" in chk:
            ok, ev = FAMILIES[df.loc[m, "family"].iloc[0]].get("kind") == chk["kind"], "family kind = aggregate"
        if not ok:
            sys.exit(f"Exclusion evidence no longer holds for {ex['file']} [{ex['sheet']}]: {ev}")
        exclude(m, f"{ex['reason']} ({ex['refs']})")
        log("R15", f"Sheet exclusion re-checked: {ex['file']} [{ex['sheet']}]", m.sum(), m.sum(), "exclude", ev)

    # test / junk rows
    test = pd.Series(False, index=df.index)
    for i in df.index:
        rx = fam[i].get("test_row_regex")
        if rx and any(re.match(rx, df.at[i, c].strip(), re.I) for c in ("date_raw", "comment_raw") if df.at[i, c].strip()):
            test[i] = True
    flag(test, "test_row")
    exclude(test, "test / junk row (I106)")
    log("R16", "Test / junk rows ('TEST', 'asdf', 01/01/1900)", n, test.sum(), "exclude",
        ", ".join(f"{f} r{r}" for f, r in df.loc[test, ["source_file", "source_row"]].itertuples(index=False)))

    # exact duplicate rows within a sheet (full source row, PII included, via the bronze hash)
    dup = df.duplicated(["source_file", "source_sheet", "raw_row_hash"], keep="first")
    first_row = df.groupby(["source_file", "source_sheet", "raw_row_hash"])["source_row"].transform("min")
    flag(dup, "exact_duplicate")
    for i in df.index[dup]:
        reasons[i].append(f"exact duplicate of source row {first_row[i]}")
    prev = df.groupby(["source_file", "source_sheet", "raw_row_hash"])["source_row"].shift()
    gap = (df["source_row"] - prev)[dup].astype(int)
    log("R17", "No exact duplicate rows within a sheet", n, dup.sum(), "exclude later copies, keep the first",
        "; ".join(f"{f}: {len(g)} (rows after the previous copy: { {int(k): int(v) for k, v in gap[g.index].value_counts().sort_index().items()} })"
                  for f, g in df[dup].groupby("source_file")) + ". 1 = directly below its copy")

    # identical tabs anywhere (not only the configured one)
    h = sheets[sheets["sheet_content_hash"] != ""].groupby("sheet_content_hash")
    same = [" == ".join(f"{r.source_file} [{r.source_sheet}]" for r in g.itertuples()) for _, g in h if len(g) > 1]
    log("R18", "No identical tabs or files", len(sheets), len(same), "exclude the copy (see R15)", "; ".join(same) or "none")

    # Essendon: same date + comment + score in the Sales and the Service tab
    cross = pd.Series(False, index=df.index)
    for fname, f in {r: FAMILIES[fm] for r, fm in df[["source_file", "family"]].drop_duplicates().itertuples(index=False)}.items():
        ct = f.get("cross_tab_duplicates")
        if not ct:
            continue
        inf = df["source_file"] == fname
        kept = set(keys[inf & (df["source_sheet"] == ct["keep_sheet"]) & df["has_text"]])
        m = inf & (df["source_sheet"] == ct["drop_sheet"]) & df["has_text"] & keys.isin(kept)
        cross |= m
    flag(cross, "cross_tab_duplicate")
    exclude(cross, "same date, comment and score also in the Service tab; Service copy kept (I012, I080)")
    log("R19", "Same feedback logged in more than one tab (Essendon Sales vs Service)",
        (df["family"] == "essendon").sum(), cross.sum(), "exclude the Sales copy, keep Service",
        "only rows with comment text are matched; blank-comment rows sharing a date and score are not treated as copies")

    # anything still outside the window or after closure
    exclude(out_window, "date outside Oct 2025 - Sep 2026 window")
    flag(out_window, "date_outside_window")
    log("R20", "Date inside the Oct 2025 - Sep 2026 window", fd.notna().sum(), out_window.sum(), "exclude (after D4 fix)",
        ", ".join(f"{f} r{r}" for f, r in df.loc[out_window, ["source_file", "source_row"]].itertuples(index=False)) or "none")
    log("R21", "No feedback after a site's closure date (after D4 fix)", vic09.sum(), still_closed.sum(), "exclude", "")

    # ---- R10 rating vs comment sentiment, pooled by file family -----------------------------
    # Pool = file family + rating scale + inverted flag, so a pool never mixes scales (Ringwood 1-5 vs 1-10)
    # and the Geelong 2025 tab is tested on its own. Included rows only.
    included = pd.Series([not r for r in reasons], index=df.index)
    pos = df["comment_clean"].str.contains(POS_KW) & ~df["comment_clean"].str.contains(NEG_KW)
    neg = df["comment_clean"].str.contains(NEG_KW) & ~df["comment_clean"].str.contains(POS_KW)
    pool_rows, sent_rows = [], 0
    base = df[rated & included & x_raw.notna()]
    for (fm, sc, iv), g in base.groupby([base["family"], base["rating_scale"], inv[base.index]]):
        per_sheet = [(x_raw[t.index].min(), x_raw[t.index].max()) for _, t in g.groupby(["source_file", "source_sheet"])]
        p, q = g.index[pos[g.index]], g.index[neg[g.index]]
        sent_rows += len(p) + len(q)
        ok_n = len(p) >= 8 and len(q) >= 8
        res = {}
        for label, sco in (("fixed", df["score_norm"]), ("raw", raw_score)):
            res[label] = ("not testable" if not ok_n else
                          "FAIL (suspected inverted)" if sco[p].mean() + 12.5 <= sco[q].mean() else "pass")
        lo_, hi_ = SCALES[sc]["min"], SCALES[sc]["max"]
        pool_rows.append({
            "family": fm, "rating_scale": sc, "inverted_fixed": bool(iv), "dealers": ", ".join(sorted(g["dealer_code"].unique())),
            "sheets": len(per_sheet), "rows": len(g), "scale_min": lo_, "scale_max": hi_,
            "observed_min": x_raw[g.index].min(), "observed_max": x_raw[g.index].max(),
            "sheet_ranges": "; ".join(sorted({f"{a:g}-{b:g}" for a, b in per_sheet})),
            "consistent_min_max": bool(lo_ <= x_raw[g.index].min() and x_raw[g.index].max() <= hi_ and len({b for _, b in per_sheet}) == 1),
            "n_pos_comments": len(p), "n_neg_comments": len(q),
            "pos_mean_score": round(df["score_norm"][p].mean(), 1) if len(p) else None,
            "neg_mean_score": round(df["score_norm"][q].mean(), 1) if len(q) else None,
            "result_before_fix": res["raw"], "result_after_fix": res["fixed"]})
    pools = pd.DataFrame(pool_rows)
    pools.to_csv(OUTPUTS / "sentiment_check_pools.csv", index=False)
    testable = pools[pools["result_after_fix"] != "not testable"]
    tested_dealers = sorted({d.strip() for ds in testable["dealers"] for d in ds.split(",")})
    all_dealers = sorted(df.loc[rated & included, "dealer_code"].unique())
    fails = pools[pools["result_after_fix"].str.startswith("FAIL")]
    log("R10", "Rating vs comment sentiment, pooled by file family and scale (positive-word comments must not score lower than negative-word ones)",
        sent_rows, len(fails), "ask / fix if any pool fails",
        f"{len(testable)} of {len(pools)} pools testable, covering {len(tested_dealers)} of {len(all_dealers)} dealers; "
        f"not testable: {', '.join(sorted(set(all_dealers) - set(tested_dealers))) or 'none'}; "
        f"pools with inconsistent min/max: {', '.join(pools.loc[~pools['consistent_min_max'], 'family']) or 'none'}; "
        f"failing before the fix: {', '.join(f'{r.family} {r.rating_scale}' + (' (inverted tab)' if r.inverted_fixed else '') for r in pools[pools['result_before_fix'].str.startswith('FAIL')].itertuples()) or 'none'}; "
        f"failing after the fix: {', '.join(fails['family']) or 'none'}. Needs >= 8 positive-only and >= 8 negative-only comments and a gap >= 12.5 points. "
        "Detail: outputs/sentiment_check_pools.csv")

    # ---- assemble -------------------------------------------------------------------------
    df["dq_flags"] = [";".join(dict.fromkeys(f)) for f in flags]
    df["excluded"] = [bool(r) for r in reasons]
    df["exclude_reason"] = ["; ".join(r) for r in reasons]
    df["feedback_id"] = [f"{dc}-{hashlib.sha1(f'{f}|{s}|{r}'.encode()).hexdigest()[:10]}"
                         for dc, f, s, r in zip(df["dealer_code"], df["source_file"], df["source_sheet"], df["source_row"])]
    df["feedback_date"] = [d.isoformat() if d else "" for d in df["feedback_date"]]
    silver = df[SILVER_COLUMNS]
    silver.to_csv(SILVER / "feedback_silver.csv", index=False, encoding="utf-8")

    # ---- exclusions report --------------------------------------------------------------
    ex = silver[silver["excluded"]].copy()
    ex["reason_group"] = ex["exclude_reason"].str.replace(r"of source row \d+", "of an earlier row", regex=True)
    groups = (ex.groupby(["reason_group", "source_file", "source_sheet"])
                .agg(rows=("source_row", "size"), source_rows=("source_row", lambda s: ", ".join(map(str, sorted(s)))))
                .reset_index().sort_values("rows", ascending=False))
    groups.to_csv(OUTPUTS / "exclusions.csv", index=False)

    rl = pd.DataFrame(rules)
    rl.to_csv(OUTPUTS / "dq_rule_log.csv", index=False)

    # ---- checks ---------------------------------------------------------------------------
    bronze_data = int((bronze["row_class"] == "data").sum())
    checks = {
        "silver rows == bronze data rows": len(silver) == bronze_data,
        "included + excluded == total": int((~silver["excluded"]).sum() + silver["excluded"].sum()) == len(silver),
        "feedback_id unique": silver["feedback_id"].is_unique,
        "every excluded row has a reason": bool((silver.loc[silver["excluded"], "exclude_reason"] != "").all()),
        "no PII pattern left in comment_clean": not left.any(),
        "no staff name left in comment_clean (token-by-token, any case)": not staff_left.any(),
        "all dealer codes valid": not bad.any(),
        "no included row outside the window": not (out_window & ~silver["excluded"]).any(),
        "no included row after closure": not (still_closed & ~silver["excluded"]).any(),
        "score_norm within 0-100": bool(silver["score_norm"].dropna().between(0, 100).all()),
        "no pool fails the sentiment check after the fix": fails.empty,
        "every sentiment pool has a consistent min and max": bool(pools["consistent_min_max"].all()),
    }
    no_month = int(((silver["month"] == "") & ~silver["excluded"]).sum())
    write_report(silver, rl, groups, bronze, sheets, checks, no_month)
    inc = silver[~silver["excluded"]]
    print(f"silver rows {len(silver)} | included {len(inc)} | excluded {int(silver['excluded'].sum())} | "
          f"with text {int(inc['has_text'].sum())} | included rows without a month {no_month}")
    for k, v in checks.items():
        print(f"  [{'PASS' if v else 'FAIL'}] {k}")
    if not all(checks.values()):
        sys.exit(1)


def md_table(df):
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in df.itertuples(index=False):
        lines.append("| " + " | ".join(str(v).replace("|", "/").replace("\n", " ") for v in r) + " |")
    return "\n".join(lines)


def write_report(silver, rl, groups, bronze, sheets, checks, no_month):
    inc = silver[~silver["excluded"]]
    by_reason = (silver[silver["excluded"]].assign(r=silver["exclude_reason"].str.replace(r"of source row \d+", "of an earlier row", regex=True))
                 .groupby("r").size().sort_values(ascending=False).reset_index(name="rows").rename(columns={"r": "exclude_reason"}))
    recon = pd.read_csv(OUTPUTS / "bronze_reconciliation.csv")
    cls = bronze["row_class"].value_counts()
    txt = f"""# Data quality report (silver)

Generated by `02_silver.py` from `data/bronze/`. No LLM calls. Counts only; no personal data appears here.

## Reconciliation

| Step | Rows |
|---|---|
| Feedback files read | {sheets['source_file'].nunique()} files, {len(sheets)} sheets |
| Bronze non-blank rows | {len(bronze)} (data {cls.get('data', 0)}, header {cls.get('header', 0)}, banner {cls.get('banner', 0)}, total {cls.get('total', 0)}, note {cls.get('note', 0)}) |
| Bronze data rows vs profiling Manifest | {int(recon['bronze_data_rows'].sum())} vs {int(recon['manifest_rows'].sum())}; {int(recon['match'].sum())} of {len(recon)} file/sheets match |
| Silver rows (= bronze data rows) | {len(silver)} |
| Excluded (kept, excluded = true) | {int(silver['excluded'].sum())} |
| Included | {len(inc)} |
| Included with a score | {int(inc['score_norm'].notna().sum())} |
| Included with comment text | {int(inc['has_text'].sum())} (customer voice {int((inc['voice'] == 'customer').sum())}, staff paraphrased {int((inc['voice'] == 'staff_paraphrased').sum())}) |
| Included without a month | {no_month} |

Non-data bronze rows (headers, banners, monthly total rows, footer notes) are not feedback and are not carried into silver; they stay in `data/bronze/bronze_rows.csv` with their row class.

## Validation rules

{md_table(rl)}

## Exclusions by reason

{md_table(by_reason)}

Full list by file and sheet, with source rows: `outputs/exclusions.csv`.

## Checks

{chr(10).join(f"- [{'x' if v else ' '}] {k}" for k, v in checks.items())}
"""
    (OUTPUTS / "quality_report.md").write_text(txt, encoding="utf-8")


if __name__ == "__main__":
    main()
