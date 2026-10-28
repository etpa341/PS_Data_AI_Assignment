"""Tests for 03_label.py, 04_evaluate.py and 05_gold.py on fake clients and dummy data.
No LLM calls; never reads or writes labelling/labelling_sheet.xlsx.   Run:  python -m pytest -q tests
"""
import importlib.util
import json
import math
import sys
from pathlib import Path

import pandas as pd
import pytest
from openpyxl import Workbook

ROOT = Path(__file__).resolve().parent.parent
sys.dont_write_bytecode = True


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / file)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


label = load("label", "03_label.py")
evaluate = load("evaluate", "04_evaluate.py")
gold = load("gold", "05_gold.py")
SILVER = pd.read_csv(ROOT / "data" / "silver" / "feedback_silver.csv", dtype=str, keep_default_na=False)


def small_silver(tmp_path, n_text=6):
    """A few labelled-type rows plus one row of every other status."""
    cust = SILVER[(SILVER.excluded == "False") & (SILVER.voice == "customer") & (SILVER.has_text == "True")].head(n_text)
    inc = SILVER[SILVER.excluded == "False"]
    other = pd.concat([inc[inc.has_text == "False"].head(1), inc[inc.voice == "staff_paraphrased"].head(1),
                       SILVER[SILVER.excluded == "True"].head(1)])
    p = tmp_path / "silver.csv"
    pd.concat([cust, other]).to_csv(p, index=False)
    return p, cust


# ---------------------------------------------------------------- 03_label.py
def test_schema_validation():
    ok = {"primary_theme": "Price and billing", "secondary_theme": None, "sentiment": "negative", "confidence": 0.8}
    assert label.parse_and_validate(json.dumps(ok))[0] == ok
    assert label.parse_and_validate("```json\n" + json.dumps(ok) + "\n```")[0] == ok
    for bad in [dict(ok, primary_theme="Pricing"), dict(ok, sentiment="angry"), dict(ok, confidence=1.5),
                dict(ok, secondary_theme="Price and billing"), {k: v for k, v in ok.items() if k != "confidence"},
                dict(ok, extra=1), dict(ok, confidence=True)]:
        assert label.parse_and_validate(json.dumps(bad))[0] is None
    assert label.parse_and_validate("not json")[0] is None


def test_label_statuses_retry_and_cache(tmp_path):
    sp, cust = small_silver(tmp_path)
    first = cust["comment_clean"].iloc[0]
    fake = label.FakeClient(fail_first_for=[first])
    summary, out = label.run(["--dry-run", "--out-dir", str(tmp_path / "lab")], client=fake, silver_path=sp)
    assert len(out) == len(cust) + 3                                   # nothing dropped
    assert summary["status_counts"] == {"labelled": 6, "no_comment": 1, "skipped_voice": 1, "skipped_excluded": 1}
    assert fake.calls == 7                                             # 6 texts + 1 retry; no call for the other 3 rows
    retried = out[out.feedback_id == cust["feedback_id"].iloc[0]].iloc[0]
    assert retried.attempts == 2 and retried.label_status == "labelled"
    # second run: everything from the cache, no calls
    fake2 = label.FakeClient()
    summary2, _ = label.run(["--dry-run", "--out-dir", str(tmp_path / "lab")], client=fake2, silver_path=sp)
    assert fake2.calls == 0 and summary2["cache_hits"] == 6


def test_failed_validation_after_one_retry(tmp_path):
    sp, cust = small_silver(tmp_path, n_text=2)

    class Broken:
        calls = 0

        def complete(self, system, user):
            Broken.calls += 1
            return "{oops"
    summary, out = label.run(["--dry-run", "--out-dir", str(tmp_path / "lab")], client=Broken(), silver_path=sp)
    assert Broken.calls == 4                                           # 2 texts x (1 try + 1 retry)
    assert summary["status_counts"]["failed_validation"] == 2
    assert out.loc[out.label_status == "failed_validation", "error"].str.contains("not JSON").all()
    # failures are retried on the next run, not served from the cache
    fake = label.FakeClient()
    label.run(["--dry-run", "--out-dir", str(tmp_path / "lab")], client=fake, silver_path=sp)
    assert fake.calls == 2


def test_prompt_drift_stops_run(tmp_path):
    sp, _ = small_silver(tmp_path, n_text=1)
    d = tmp_path / "lab"
    label.run(["--dry-run", "--out-dir", str(d)], client=label.FakeClient(), silver_path=sp)
    lines = [json.loads(x) for x in (d / "cache.jsonl").read_text(encoding="utf-8").splitlines()]
    lines[0]["prompt_sha"] = "changed"
    (d / "cache.jsonl").write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        label.run(["--dry-run", "--out-dir", str(d)], client=label.FakeClient(), silver_path=sp)


def test_cache_key_depends_on_text_version_model():
    k = label.cache_key("a", "v1", "m")
    assert k != label.cache_key("a", "v2", "m") and k != label.cache_key("a", "v1", "n") and k != label.cache_key("b", "v1", "m")


# ---------------------------------------------------------------- 04_evaluate.py
def test_kappa_and_wilson():
    assert math.isclose(evaluate.cohen_kappa(list("aabb"), list("abbb")), 0.5)
    assert evaluate.cohen_kappa(list("abc"), list("abc")) == 1
    lo, hi = evaluate.wilson(50, 100)
    assert 0.40 < lo < 0.41 and 0.59 < hi < 0.60


def dummy_sheet(path, ids, themes, sents, voice_ids=(), voice_vals=()):
    wb = Workbook()
    ws = wb.active
    ws.title = "Labels"
    ws.append(["feedback_id", "dealer_code", "department", "comment_clean", "my_primary_theme", "my_secondary_theme", "my_sentiment", "notes"])
    for i, t, s in zip(ids, themes, sents):
        r = SILVER.set_index("feedback_id").loc[i]
        ws.append([i, r.dealer_code, r.department, r.comment_clean, t, None, s, None])
    wv = wb.create_sheet("Voice_check")
    wv.append(["feedback_id", "dealer_code", "comment_clean", "my_voice"])
    for i, v in zip(voice_ids, voice_vals):
        wv.append([i, "", "", v])
    wb.save(path)


def test_evaluate_on_dummy_data(tmp_path):
    th = evaluate_themes = ["Staff attitude", "Communication and updates", "Wait time and turnaround", "Price and billing",
                            "Work quality and fix", "Vehicle or product", "Process and facilities", "Other"]
    se = ["positive", "neutral", "negative", "mixed"]
    pool = SILVER[(SILVER.excluded == "False") & (SILVER.voice == "customer") & (SILVER.has_text == "True")]
    ids = list(pool.sample(40, random_state=1).feedback_id)
    h_theme = [th[i % 8] for i in range(40)]
    h_sent = [se[i % 4] for i in range(40)]
    a_theme = [t if i < 30 else th[(th.index(t) + 1) % 8] for i, t in enumerate(h_theme)]   # 30/40 agree
    a_sent = [s if i % 5 else se[(se.index(s) + 1) % 4] for i, s in enumerate(h_sent)]     # 32/40 agree
    sheet = tmp_path / "dummy_sheet.xlsx"
    staff_ids = list(SILVER[SILVER.voice == "staff_paraphrased"].feedback_id[:4])
    cust_ids = list(pool.feedback_id[:4])
    dummy_sheet(sheet, ids, h_theme, h_sent, staff_ids + cust_ids, ["staff", "staff", "staff", "customer", "customer"] + ["customer"] * 3)
    labels = pd.DataFrame({"feedback_id": SILVER.feedback_id, "label_status": "skipped_voice"})
    labels = labels.set_index("feedback_id")
    labels.loc[ids, "label_status"] = "labelled"
    labels.loc[ids, "primary_theme"] = a_theme
    labels.loc[ids, "secondary_theme"] = ""
    labels.loc[ids, "sentiment"] = a_sent
    labels.loc[ids, "confidence"] = "0.9"
    # Ringwood 1-10 rows: negative for 1-4, positive above
    ring = SILVER[(SILVER.excluded == "False") & (SILVER.rating_scale == "num_1_10")]
    ring_ids = [i for i in ring.feedback_id if i not in ids]
    labels.loc[ring_ids, "label_status"] = "labelled"
    labels.loc[ring_ids, "sentiment"] = ["negative" if int(r) <= 4 else "positive" for r in ring.set_index("feedback_id").loc[ring_ids, "rating_raw"]]
    lp = tmp_path / "labels.csv"
    labels.reset_index().to_csv(lp, index=False)
    res, vres, rres = evaluate.main(["--sheet", str(sheet), "--labels", str(lp), "--out", str(tmp_path / "ev")])
    assert res["scored"] == 40
    assert math.isclose(res["theme_accuracy"], 30 / 40)
    assert math.isclose(res["sentiment_accuracy"], 32 / 40)
    assert -1 <= res["theme_kappa"] <= 1 and res["theme_kappa"] < 1
    errs = pd.read_csv(tmp_path / "ev" / "errors.csv")
    assert len(errs) == 10 and "reviewer_reason" in errs
    assert vres["n"] == 8 and math.isclose(vres["staff_tag_precision"], 3 / 4) and math.isclose(vres["staff_tag_recall"], 1.0)
    assert rres["strict_1_4_mostly_negative"] and rres["headline_at_risk_le5"] <= rres["sensitivity_at_risk_le6"]
    assert (tmp_path / "ev" / "evaluation_report.md").exists()


def test_evaluate_rejects_empty_sheet(tmp_path):
    sheet = tmp_path / "empty.xlsx"
    dummy_sheet(sheet, [], [], [])
    with pytest.raises(SystemExit):
        evaluate.main(["--sheet", str(sheet), "--labels", str(tmp_path / "x.csv"), "--out", str(tmp_path / "ev")])


# ---------------------------------------------------------------- 05_gold.py
def test_gold_gaps_are_missing_not_zero(tmp_path):
    gold.main(["--no-labels", "--out", str(tmp_path / "g")])
    p = pd.read_csv(tmp_path / "g" / "dealer_month_dept.csv")
    pen = p[(p.dealer_code == "NSW02") & (p.month == "2026-06")]
    toow = p[(p.dealer_code == "QLD06") & p.month.isin(["2025-10", "2025-11", "2025-12"])]
    assert pen.responses.isna().all() and toow.responses.isna().all()
    assert pen.gap_reason.str.startswith("D5").all() and toow.gap_reason.str.startswith("D5").all()
    assert (pen.revenue_aud > 0).all()
    other = p[p.gap_reason.isna()]
    assert other.responses.notna().all()


# ---------------------------------------------------------------- select_model.py
def test_newest_haiku_selected_from_key_list():
    sm = load("select_model", "select_model.py")
    models = [{"id": "claude-haiku-4-5-20251001", "display_name": "Claude Haiku 4.5", "created_at": "2025-10-01T00:00:00Z"},
              {"id": "claude-opus-5-5", "display_name": "Claude Opus 5.5", "created_at": "2026-09-01T00:00:00Z"},
              {"id": "claude-haiku-5-5", "display_name": "Claude Haiku 5.5", "created_at": "2026-06-01T00:00:00Z"}]
    best, haiku = sm.newest_haiku(models)
    assert best["id"] == "claude-haiku-5-5" and [m["id"] for m in haiku] == ["claude-haiku-5-5", "claude-haiku-4-5-20251001"]
    with pytest.raises(SystemExit):
        sm.newest_haiku([models[1]])


# ---------------------------------------------------------------- prompts/classify_v1.txt
def test_prompt_matches_schema_and_definitions():
    p = (ROOT / "prompts" / "classify_v1.txt").read_text(encoding="utf-8")
    for t in label.THEMES:
        assert f". {t}: " in p
    for s in label.SENTIMENTS:
        assert f"- {s}: " in p
    assert "overall verdict" in p and "never given the customer's rating" in p
    ls = p.splitlines()
    outs = [json.loads(ls[i + 1]) for i, line in enumerate(ls[:-1]) if line.startswith("<comment>")]
    assert 4 <= len(outs) <= 6 and all(label.parse_and_validate(json.dumps(o))[0] == o for o in outs)
    assert {"mixed", "negative", "neutral", "positive"} <= {o["sentiment"] for o in outs}
