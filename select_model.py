"""
select_model.py - pick the labelling model from the models available to this API key.

Lists models with GET https://api.anthropic.com/v1/models (a free metadata call, not a
completion), keeps those whose id or display name contains "haiku", and selects the newest by
created_at. Writes the id, display name, date and the Haiku list into config/settings.yaml and
appends a line to ai_usage_log.md. Stops if the selected model has no price in settings
(pricing.by_model); add it from the pricing source URL first.

Needs ANTHROPIC_API_KEY in the environment.   Run:  python select_model.py [--dry-list]
"""
import json
import os
import re
import sys
import urllib.request
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
SETTINGS = ROOT / "config" / "settings.yaml"
LOG = ROOT / "ai_usage_log.md"


def list_models(key):
    models, after = [], None
    while True:
        url = "https://api.anthropic.com/v1/models?limit=1000" + (f"&after_id={after}" if after else "")
        req = urllib.request.Request(url, headers={"x-api-key": key, "anthropic-version": "2023-06-01"})
        with urllib.request.urlopen(req, timeout=30) as r:
            page = json.load(r)
        models += page["data"]
        if not page.get("has_more"):
            return models
        after = page["last_id"]


def newest_haiku(models):
    haiku = [m for m in models if "haiku" in (m["id"] + " " + m.get("display_name", "")).lower()]
    if not haiku:
        sys.exit("No Haiku model is available to this key.")
    return max(haiku, key=lambda m: m["created_at"]), sorted(haiku, key=lambda m: m["created_at"], reverse=True)


def set_line(text, key, value):
    new, n = re.subn(rf"^(  {key}:) .*$", lambda m: f"{m.group(1)} {value}", text, count=1, flags=re.M)
    if n != 1:
        sys.exit(f"settings.yaml: could not find llm.{key}")
    return new


def load_env_file(path=ROOT / ".env"):
    """Set ANTHROPIC_API_KEY from a gitignored .env (KEY=value lines) if it is not already in the environment."""
    if os.environ.get("ANTHROPIC_API_KEY") or not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        k, sep, v = line.strip().partition("=")
        if sep and k.strip() == "ANTHROPIC_API_KEY":
            os.environ["ANTHROPIC_API_KEY"] = v.strip().strip('"').strip("'")


def main():
    load_env_file()
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        sys.exit("ANTHROPIC_API_KEY is not set. Set it in the environment (never in the repo) and rerun.")
    models = list_models(key)
    best, haiku = newest_haiku(models)
    cfg = yaml.safe_load(SETTINGS.read_text(encoding="utf-8"))
    price = cfg["pricing"]["by_model"].get(best.get("display_name"))
    print(f"{len(models)} models available; Haiku models (newest first): " + ", ".join(m["id"] for m in haiku))
    print(f"selected: {best['id']} ({best.get('display_name')}, created {best['created_at']})")
    if "--dry-list" in sys.argv:
        return
    if price is None:
        sys.exit(f"No price for {best.get('display_name')!r} in settings pricing.by_model. Add it from {cfg['pricing']['source_url']} first.")
    t = SETTINGS.read_text(encoding="utf-8")
    t = set_line(t, "model", best["id"])
    t = set_line(t, "model_confirmed", "true")
    t = set_line(t, "model_display_name", json.dumps(best.get("display_name")))
    t = set_line(t, "model_selected_on", date.today().isoformat())
    t = set_line(t, "haiku_models_available", json.dumps([m["id"] for m in haiku]))
    SETTINGS.write_text(t, encoding="utf-8")
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(f"\n- {date.today().isoformat()}: model selected by select_model.py from GET /v1/models for this key: "
                 f"`{best['id']}` ({best.get('display_name')}), the newest of {len(haiku)} Haiku models available. "
                 f"Price ${price['input']}/${price['output']} per M input/output tokens, from {cfg['pricing']['source_url']} "
                 f"(checked {cfg['pricing']['checked_on']}).\n")
    print("settings.yaml and ai_usage_log.md updated")


if __name__ == "__main__":
    main()
