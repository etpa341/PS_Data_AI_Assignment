"""
build_prompt.py - write prompts/classify_v1.txt from the final Definitions tab (single source).

Reads labelling/labelling_sheet.xlsx -> Definitions (read-only): the 8 themes with definitions and
example comment types, the sentiment definitions, the boundary rules, the credit rule and the SPEC 9 rules.
Adds the fixed output contract (matching 03_label.py's schema check) and invented worked examples.
Refuses to overwrite an existing prompt version with different text: bump prompt.version instead.
Writes prompts/classify_<version>.meta.json with the source and hashes.

No LLM calls.   Run:  python build_prompt.py
"""
import hashlib
import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent
SHEET = ROOT / "labelling" / "labelling_sheet.xlsx"
SETTINGS = yaml.safe_load((ROOT / "config" / "settings.yaml").read_text(encoding="utf-8"))
VERSION = SETTINGS["prompt"]["version"]
OUT = ROOT / SETTINGS["prompt"]["file"]
THEMES = SETTINGS["labels"]["themes"]
SENTIMENTS = SETTINGS["labels"]["sentiments"]

# Invented examples (not taken from the data; checked against silver below). One mixed, one sarcastic.
EXAMPLES = [
    ("Made a 9am appointment on the website, but the service desk had nothing in their system. Nobody rang later to explain.",
     {"primary_theme": "Process and facilities", "secondary_theme": "Communication and updates", "sentiment": "negative", "confidence": 0.85}),
    ("Lovely people at the front desk, but the invoice came to $180 more than the quote.",
     {"primary_theme": "Price and billing", "secondary_theme": "Staff attitude", "sentiment": "mixed", "confidence": 0.8}),
    ("Oh brilliant, third visit for the same rattle. Really loving spending my Saturdays at your workshop.",
     {"primary_theme": "Work quality and fix", "secondary_theme": None, "sentiment": "negative", "confidence": 0.85}),
    ("ok",
     {"primary_theme": "Other", "secondary_theme": None, "sentiment": "neutral", "confidence": 0.9}),
    ("The part was on back-order for three weeks and I had to chase them for every update.",
     {"primary_theme": "Wait time and turnaround", "secondary_theme": "Communication and updates", "sentiment": "negative", "confidence": 0.8}),
    ("[STAFF] tracked down the fault the last two places missed. Drives like new.",
     {"primary_theme": "Work quality and fix", "secondary_theme": "Staff attitude", "sentiment": "positive", "confidence": 0.8}),
]


def main():
    d = pd.read_excel(SHEET, sheet_name="Definitions", dtype=str).fillna("")
    get = lambda prefix: d[d["item"].str.startswith(prefix)]
    themes = get("Theme ")
    names = [i.split(": ", 1)[1] for i in themes["item"]]
    if names != THEMES:
        sys.exit(f"Definitions tab themes {names} do not match settings labels.themes {THEMES}")
    sents = get("Sentiment: ")
    if [i.split(": ", 1)[1] for i in sents["item"]] != ["positive", "neutral", "negative", "mixed"] or set(SENTIMENTS) != {"positive", "neutral", "negative", "mixed"}:
        sys.exit("Definitions tab sentiments do not match settings")
    boundary = get("Boundary rule")["text"].tolist()
    credit = get("Credit rule")["text"].tolist()
    rules = dict(zip(get("SPEC 9 rule")["item"], get("SPEC 9 rule")["text"]))
    if not boundary or not credit or "overall verdict" not in rules.get("SPEC 9 rule 5", ""):
        sys.exit("Definitions tab is missing boundary rules, the credit rule, or the 'overall verdict' rule 5")

    lines = [
        "You classify one customer feedback comment left at a car dealership group (vehicle sales, servicing and parts).",
        "You see the comment text only. You are never given the customer's rating, so judge only from the words.",
        "The comment arrives between <comment> and </comment>. Placeholders such as [STAFF], [NAME], [PHONE], [EMAIL] and [REGO] replace personal details that were removed; [STAFF] is a staff member.",
        "",
        "THEMES (use these exact names)",
    ]
    for i, (n, r) in enumerate(zip(names, themes.itertuples()), 1):
        lines.append(f"{i}. {n}: {r.text} Example: {r.example_comment_type}")
    lines += ["", "HOW TO CHOOSE THEMES",
              f"- {rules['SPEC 9 rule 5']}",
              "- secondary_theme is optional: use it only when a second theme is clearly present, otherwise null. It must differ from primary_theme.",
              f"- {rules['SPEC 9 rule 4']} (secondary_theme null).",
              f"- Credit rule: {credit[0]}"]
    lines += [f"- {b}" for b in boundary]
    lines += ["", "SENTIMENT (use these exact values)"]
    for r in sents.itertuples():
        lines.append(f"- {r.item.split(': ', 1)[1]}: {r.text}")
    lines += ["", "CONFIDENCE",
              "- A number from 0 to 1: how sure you are of primary_theme and sentiment together. Use lower values for short, vague or ambiguous comments.",
              "", "OUTPUT",
              "Reply with one JSON object and nothing else: no prose, no code fence. Exactly these four keys:",
              '{"primary_theme": <one of the 8 theme names>, "secondary_theme": <a different theme name or null>, "sentiment": <positive|neutral|negative|mixed>, "confidence": <number 0-1>}',
              "", "EXAMPLES (invented, for illustration only)"]
    for text, out in EXAMPLES:
        lines += [f"<comment>{text}</comment>", json.dumps(out)]
    prompt = "\n".join(lines) + "\n"

    # examples must be valid output and must not come from the data
    sys.dont_write_bytecode = True
    import importlib.util
    spec = importlib.util.spec_from_file_location("label", ROOT / "03_label.py")
    lab = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lab)
    for text, out in EXAMPLES:
        assert lab.parse_and_validate(json.dumps(out))[0] == out, out
    silver = pd.read_csv(ROOT / "data" / "silver" / "feedback_silver.csv", dtype=str, keep_default_na=False)
    corpus = "\n".join(silver["comment_clean"].str.lower())
    for text, _ in EXAMPLES:
        if len(text) > 10:
            for frag in [text[i:i + 30].lower() for i in range(0, len(text) - 30, 10)]:
                assert frag not in corpus, f"example fragment found in the data: {frag!r}"
    sents_used = {o["sentiment"] for _, o in EXAMPLES}
    assert "mixed" in sents_used

    if OUT.exists() and OUT.read_text(encoding="utf-8") != prompt:
        sys.exit(f"{OUT} exists with different text. Bump prompt.version in config/settings.yaml instead of overwriting {VERSION}.")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(prompt, encoding="utf-8")
    meta = {"prompt_version": VERSION, "prompt_sha": hashlib.sha256(prompt.encode()).hexdigest()[:12],
            "definitions_source": "labelling/labelling_sheet.xlsx, tab Definitions",
            "definitions_sha": hashlib.sha256(d.to_csv(index=False).encode()).hexdigest()[:12],
            "built_on": date.today().isoformat(), "examples": "invented; checked absent from data/silver (30-character fragments)"}
    OUT.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({len(prompt)} chars, ~{len(prompt)//4} tokens), sha {meta['prompt_sha']}")


if __name__ == "__main__":
    main()
