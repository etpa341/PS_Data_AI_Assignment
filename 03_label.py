"""
03_label.py - classify comments with the LLM, cached and reproducible offline (SPEC section 9).

Every silver row gets exactly one output row with a label_status, so nothing is excluded silently:
  labelled            customer-voice row with text, valid JSON from the model (or the cache)
  no_comment          no comment text; tagged without a call
  skipped_voice       text written up by staff, or voice unknown (themes use customer voice only)
  skipped_excluded    row excluded in silver (exclude_reason there)
  failed_validation   invalid JSON / schema twice (first try + one retry); raw responses kept in the cache
  not_in_cache        offline mode and no cached answer yet

Modes (one of):
  (default)  --offline   cache only, never calls the API
  --live                 call the API for texts not in the cache (needs ANTHROPIC_API_KEY, prompt file, `pip install anthropic`)
  --dry-run              fake client, stub prompt, writes to data/silver_labels_dryrun (never touches the real cache)
  --estimate             count calls and approximate cost for a full live run; no calls
Options: --limit N  (label at most N uncached texts this run; for a small live trial)
         --workers N (parallel API calls in live mode; default 1)

Cache: <out_dir>/cache.jsonl, key = sha256(redacted text + prompt version + model). Raw responses are
stored so the pipeline reruns offline. If the prompt text changes without a version bump the run stops.

Run:  python 03_label.py [--live | --dry-run] [--limit N] [--workers N]
"""
import argparse
import hashlib
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent
SETTINGS = yaml.safe_load((ROOT / "config" / "settings.yaml").read_text(encoding="utf-8"))
SILVER = ROOT / "data" / "silver" / "feedback_silver.csv"
THEMES = SETTINGS["labels"]["themes"]
SENTIMENTS = SETTINGS["labels"]["sentiments"]
DRY_RUN_PROMPT = ("DRY-RUN STUB PROMPT (not a real prompt). Return JSON with primary_theme, secondary_theme, "
                  "sentiment, confidence.")
OUT_COLUMNS = ["feedback_id", "label_status", "primary_theme", "secondary_theme", "sentiment", "confidence",
               "model", "prompt_version", "prompt_sha", "run_date", "cache_key", "attempts", "error"]


# --------------------------------------------------------------------------------------
# Schema validation (no external dependency)
# --------------------------------------------------------------------------------------
def parse_and_validate(text):
    """Return (dict, "") if valid, else (None, reason)."""
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)            # tolerate a code fence, nothing else
    try:
        obj = json.loads(t)
    except json.JSONDecodeError as e:
        return None, f"not JSON: {e.msg}"
    if not isinstance(obj, dict):
        return None, "not a JSON object"
    want = {"primary_theme", "secondary_theme", "sentiment", "confidence"}
    if set(obj) != want:
        return None, f"keys {sorted(obj)} != {sorted(want)}"
    if obj["primary_theme"] not in THEMES:
        return None, f"primary_theme not allowed: {obj['primary_theme']!r}"
    if obj["secondary_theme"] is not None and (obj["secondary_theme"] not in THEMES or obj["secondary_theme"] == obj["primary_theme"]):
        return None, f"secondary_theme not allowed: {obj['secondary_theme']!r}"
    if obj["sentiment"] not in SENTIMENTS:
        return None, f"sentiment not allowed: {obj['sentiment']!r}"
    c = obj["confidence"]
    if isinstance(c, bool) or not isinstance(c, (int, float)) or not 0 <= c <= 1:
        return None, f"confidence not a number in 0-1: {c!r}"
    return obj, ""


def cache_key(text, prompt_version, model):
    return hashlib.sha256(f"{text}\x1f{prompt_version}\x1f{model}".encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------------------
# Clients: complete(system, user) -> str
# --------------------------------------------------------------------------------------
def load_env_file(path=ROOT / ".env"):
    """Set ANTHROPIC_API_KEY from a gitignored .env (KEY=value lines) if it is not already in the environment."""
    if os.environ.get("ANTHROPIC_API_KEY") or not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        k, sep, v = line.strip().partition("=")
        if sep and k.strip() == "ANTHROPIC_API_KEY":
            os.environ["ANTHROPIC_API_KEY"] = v.strip().strip('"').strip("'")


class AnthropicClient:
    def __init__(self, cfg):
        load_env_file()
        if not os.environ.get("ANTHROPIC_API_KEY"):
            sys.exit("ANTHROPIC_API_KEY is not set (it is read from the environment only).")
        try:
            import anthropic
        except ImportError:
            sys.exit("The anthropic package is not installed: pip install anthropic")
        # the SDK retries 429/5xx with backoff; raised from its default 2 for parallel workers
        self.client = anthropic.Anthropic(timeout=cfg["timeout_seconds"], max_retries=8)
        self.cfg = cfg
        self.usage = {"input_tokens": 0, "output_tokens": 0, "stop_reasons": {}}   # for the run log
        self._lock = threading.Lock()

    def complete(self, system, user):
        # No temperature: the current Messages API has no sampling parameters. Reruns are made
        # reproducible by the cache, which stores every raw response. max_tokens covers the model's
        # default thinking as well as the JSON answer.
        r = self.client.messages.create(model=self.cfg["model"], max_tokens=self.cfg["max_tokens"],
                                        system=system, messages=[{"role": "user", "content": user}])
        with self._lock:
            self.usage["input_tokens"] += r.usage.input_tokens
            self.usage["output_tokens"] += r.usage.output_tokens
            self.usage["stop_reasons"][r.stop_reason] = self.usage["stop_reasons"].get(r.stop_reason, 0) + 1
        return "".join(b.text for b in r.content if getattr(b, "type", "") == "text")


class FakeClient:
    """Deterministic keyword stand-in for tests and dry runs. Not a classifier."""
    RULES = [("Staff attitude", r"rude|friendly|helpful|attitude|polite|sarcastic|impatient"),
             ("Communication and updates", r"update|call|rang|explain|told|message|text"),
             ("Wait time and turnaround", r"wait|waited|slow|quick|fast|days|hour|delay"),
             ("Price and billing", r"price|cost|bill|charge|invoice|quote|\$"),
             ("Work quality and fix", r"fix|fixed|repair|rattle|again|still"),
             ("Vehicle or product", r"car |model|feature|corsa|vista|terra")]

    def __init__(self, fail_first_for=()):
        self.calls = 0
        self.fail_first_for = set(fail_first_for)   # texts whose first answer is invalid (retry test)
        self.seen = set()

    def complete(self, system, user):
        self.calls += 1
        text = re.sub(r"</?comment>", "", user).strip()
        if text in self.fail_first_for and text not in self.seen:
            self.seen.add(text)
            return "Sure! Here is the JSON: {primary_theme: oops}"
        lo = text.lower()
        hits = [t for t, rx in self.RULES if re.search(rx, lo)]
        neg = bool(re.search(r"rude|never|waited|not happy|terrible|worst|still|no one|nobody", lo))
        pos = bool(re.search(r"great|thank|friendly|happy|excellent|helpful|good", lo))
        sent = "mixed" if neg and pos else "negative" if neg else "positive" if pos else "neutral"
        return json.dumps({"primary_theme": hits[0] if hits else "Other",
                           "secondary_theme": hits[1] if len(hits) > 1 else None,
                           "sentiment": sent, "confidence": 0.5})


# --------------------------------------------------------------------------------------
def load_cache(path):
    entries = {}
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()
        for n, line in enumerate(lines, 1):
            if line.strip():
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    if n == len(lines):                  # a run killed mid-write: that text is simply relabelled
                        print(f"cache: ignoring truncated last line {n}")
                        continue
                    raise
                entries[e["cache_key"]] = e          # later lines win (a retry after an earlier failure)
    return entries


def estimate(silver_path, assumed_prompt_tokens=(700, 1500), retry_rate=0.03, extra_eval_calls=120):
    """Approximate calls and cost for a full live run, from the data; makes no calls.
    Tokens ~ characters / 4. Output ~ 50 tokens per answer (four short JSON fields)."""
    s = pd.read_csv(silver_path, dtype=str, keep_default_na=False)
    todo = s[(s["excluded"] == "False") & (s["has_text"] == "True") & (s["voice"] == "customer")]
    texts = todo["comment_clean"].drop_duplicates()
    pfile = ROOT / SETTINGS["prompt"]["file"]
    if pfile.exists():
        t = len(pfile.read_text(encoding="utf-8")) / 4
        assumed_prompt_tokens = (t, t)
    calls = len(texts) * (1 + retry_rate) + extra_eval_calls      # + prompt v2 on the 120-row sample
    user_tokens = (texts.str.len() / 4 + 10).mean()               # comment + <comment> wrapper
    llm, pricing = SETTINGS["llm"], SETTINGS["pricing"]
    if llm["model_confirmed"]:
        priced = {llm["model_display_name"]: pricing["by_model"][llm["model_display_name"]]}
        status = f"confirmed model {llm['model']}"
    else:
        priced = pricing["by_model"]
        status = "MODEL NOT CONFIRMED (run select_model.py with the API key); showing every priced Haiku candidate"
    out_tokens = 50
    rows = []
    for name, price in priced.items():
        for pt in sorted(set(assumed_prompt_tokens)):
            tin = calls * (pt + user_tokens)
            tout = calls * out_tokens
            rows.append({"model": name, "prompt_tokens": round(pt), "calls": round(calls), "input_tokens_m": round(tin / 1e6, 2),
                         "output_tokens_m": round(tout / 1e6, 2),
                         "cost_usd": round(tin / 1e6 * price["input"] + tout / 1e6 * price["output"], 2),
                         "cost_usd_batch": round(tin / 1e6 * price["batch_input"] + tout / 1e6 * price["batch_output"], 2)})
    summary = {"status": status, "pricing_source": pricing["source_url"], "pricing_checked_on": str(pricing["checked_on"]),
               "texts_to_label": len(texts), "rows_without_call": len(s) - len(todo),
               "mean_comment_tokens": round(user_tokens - 10, 1), "assumptions": {"retry_rate": retry_rate, "extra_eval_calls": extra_eval_calls,
               "output_tokens_per_call": out_tokens}, "scenarios": rows}
    (ROOT / "outputs").mkdir(exist_ok=True)
    (ROOT / "outputs" / "label_cost_estimate.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return summary, None


def run(argv=None, client=None, silver_path=SILVER):
    ap = argparse.ArgumentParser()
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--live", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--offline", action="store_true")
    mode.add_argument("--estimate", action="store_true", help="count calls and approximate cost; no calls")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--workers", type=int, default=1, help="parallel API calls (live mode)")
    args = ap.parse_args(argv)

    cfg = SETTINGS["llm"]
    model = cfg["model"]
    if args.estimate:
        return estimate(silver_path)
    if not args.dry_run and not cfg.get("model_confirmed"):
        sys.exit("No confirmed model in config/settings.yaml. Run select_model.py with ANTHROPIC_API_KEY set "
                 "(it picks the newest Haiku available to the key).")
    if args.dry_run:
        model = model or "dryrun-model"
        prompt, version = DRY_RUN_PROMPT, "dryrun"
        out_dir = ROOT / (args.out_dir or SETTINGS["labels"]["dry_run_out_dir"])
        client = client or FakeClient()
    else:
        pfile = ROOT / SETTINGS["prompt"]["file"]
        if not pfile.exists():
            sys.exit(f"{pfile} does not exist yet (written once the Definitions tab is final). Use --dry-run to test.")
        prompt, version = pfile.read_text(encoding="utf-8"), SETTINGS["prompt"]["version"]
        out_dir = ROOT / (args.out_dir or SETTINGS["labels"]["out_dir"])
        if args.live:
            client = client or AnthropicClient(cfg)
        else:
            client = None                                 # offline: cache only
    prompt_sha = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:12]
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_path = out_dir / "cache.jsonl"
    cache = load_cache(cache_path)
    drift = {e["prompt_sha"] for e in cache.values() if e["prompt_version"] == version and e["model"] == model} - {prompt_sha}
    if drift:
        sys.exit(f"Prompt text changed but version is still {version!r} (cached sha {drift}, now {prompt_sha}). Bump prompt.version.")

    s = pd.read_csv(silver_path, dtype=str, keep_default_na=False)
    status = pd.Series("labelled", index=s.index)
    status[s["voice"] != "customer"] = "skipped_voice"
    status[s["has_text"] != "True"] = "no_comment"
    status[s["excluded"] == "True"] = "skipped_excluded"
    todo = s[status == "labelled"]
    texts = list(dict.fromkeys(todo["comment_clean"]))     # unique texts, file order
    keys = {t: cache_key(t, version, model) for t in texts}

    def label_one(t):
        raws, obj, err = [], None, ""
        for _ in range(1 + cfg["retries_on_invalid"]):
            raw = client.complete(prompt, f"<comment>\n{t}\n</comment>")
            raws.append(raw)
            obj, err = parse_and_validate(raw)
            if obj:
                break
            if cfg.get("pause_seconds"):
                time.sleep(cfg["pause_seconds"])
        if args.live and cfg.get("pause_seconds"):
            time.sleep(cfg["pause_seconds"])
        return {"cache_key": keys[t], "model": model, "prompt_version": version, "prompt_sha": prompt_sha,
                "valid": obj is not None, "parsed": obj, "raw_responses": raws, "error": err,
                "attempts": len(raws), "created": datetime.now(timezone.utc).strftime("%Y-%m-%d")}

    pending = [t for t in texts if not (keys[t] in cache and cache[keys[t]]["valid"])]
    hits = len(texts) - len(pending)
    if client is None:
        pending = []
    pending = pending[:args.limit] if args.limit is not None else pending
    calls, new_fail = 0, 0
    # Results are written by this thread only, one line per text, flushed as each one finishes,
    # so an interrupted run loses at most the calls in flight and resumes from the cache.
    with cache_path.open("a", encoding="utf-8") as fh, ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = [pool.submit(label_one, t) for t in pending]
        for n, f in enumerate(as_completed(futures), 1):
            e = f.result()
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")
            fh.flush()
            cache[e["cache_key"]] = e
            calls += e["attempts"]
            new_fail += not e["valid"]
            if n % 250 == 0:
                print(f"{n}/{len(pending)} labelled this run, {new_fail} failed", flush=True)

    rows = []
    for i, r in s.iterrows():
        row = {"feedback_id": r["feedback_id"], "label_status": status[i], "model": model,
               "prompt_version": version, "prompt_sha": prompt_sha}
        if status[i] == "labelled":
            e = cache.get(keys[r["comment_clean"]])
            row["cache_key"] = keys[r["comment_clean"]]
            if e is None:
                row["label_status"] = "not_in_cache"
            elif not e["valid"]:
                row.update(label_status="failed_validation", error=e["error"], attempts=e["attempts"], run_date=e["created"])
            else:
                row.update(e["parsed"], attempts=e["attempts"], run_date=e["created"])
        rows.append(row)
    out = pd.DataFrame(rows).reindex(columns=OUT_COLUMNS)
    out.to_csv(out_dir / "labels.csv", index=False)
    summary = {"mode": "dry-run" if args.dry_run else "live" if args.live else "offline", "model": model,
               "prompt_version": version, "prompt_sha": prompt_sha, "silver_rows": len(s),
               "status_counts": out["label_status"].value_counts().to_dict(), "unique_texts": len(texts),
               "api_calls_this_run": calls, "cache_hits": hits, "new_failures": new_fail}
    if getattr(client, "usage", None):
        summary["usage_this_run"] = client.usage
    (out_dir / "run_log.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    if args.live:   # run_log.json is the latest run (offline reruns overwrite it); keep every live run
        with (out_dir / "run_history.jsonl").open("a", encoding="utf-8") as h:
            h.write(json.dumps({"finished_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), **summary}) + "\n")
    assert len(out) == len(s) and out["label_status"].notna().all()
    print(json.dumps(summary, indent=2))
    return summary, out


if __name__ == "__main__":
    run()
