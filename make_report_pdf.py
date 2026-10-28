"""
make_report_pdf.py - render report.md to docs/report.pdf (A4, 11pt, 2 cm margins).

report.md is the source; docs/report.pdf is generated from it and should not be edited by hand.
Markdown -> HTML with a small converter written for this report (headings, nested lists, tables, bold,
italic, code, links), then printed with a headless Edge or Chrome. Links are printed as text only: a link
in the PDF would point at this machine's file path. Checks: page count, tables present, no local paths.
No network or API calls.   Run:  python make_report_pdf.py [--max-pages 3]
"""
import html
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "report.md"
OUT = ROOT / "docs" / "report.pdf"
BROWSERS = [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            "/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser",
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
CSS = """@page { size: A4; margin: 2cm; }
body { font: 11pt/1.35 Calibri, Arial, sans-serif; margin: 0; }
h1 { font-size: 16pt; margin: 0 0 6pt; } h2 { font-size: 13pt; margin: 10pt 0 3pt; } p { margin: 5pt 0; }
table { border-collapse: collapse; margin: 4pt 0; font-size: 9.5pt; }
td, th { border: 1px solid #999; padding: 2pt 4pt; } th { background: #eee; }
code { font-size: 9pt; } ul, ol { margin: 2pt 0; padding-left: 18pt; } li { margin: 1pt 0; }
figure { margin: 4pt 0; break-inside: avoid; } figure img { width: 85%; }"""


def inline(t):
    t = html.escape(t, quote=False)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<![*\w])\*([^*]+)\*(?!\*)", r"<em>\1</em>", t)
    return re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", t)          # link text only (see docstring)


def to_html(md):
    lines, body, stack, i = md.splitlines(), [], [], 0

    def close(level=-1):
        while stack and stack[-1][0] > level:
            body.append(f"</li></{stack.pop()[1]}>")

    while i < len(lines):
        line, s = lines[i], lines[i].strip()
        if s.startswith("|"):
            close()
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            body.append("<table><tr>" + "".join(f"<th>{inline(c)}</th>" for c in rows[0]) + "</tr>")
            body += ["<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in rows[2:]]
            body.append("</table>")
            continue
        img = re.match(r"^!\[([^\]]*)\]\(([^)]+)\)$", s)
        if img:                                                  # image on its own line: embedded, full width
            close()
            path = (ROOT / img.group(2)).resolve()
            if not path.exists():
                sys.exit(f"image not found: {img.group(2)}")
            body.append(f"<figure><img src='{path.as_uri()}' alt='{html.escape(img.group(1), quote=True)}'></figure>")
            i += 1
            continue
        m = re.match(r"^(\s*)([-*]|\d+\.)\s+(.*)", line)
        if m:
            level, kind = len(m.group(1)) // 2, ("ol" if m.group(2)[0].isdigit() else "ul")
            if stack and stack[-1][0] == level:
                body.append("</li>")
            elif stack and stack[-1][0] > level:
                close(level)
                body.append("</li>")
            if not stack or stack[-1][0] < level:
                body.append(f"<{kind}>")
                stack.append((level, kind))
            body.append(f"<li>{inline(m.group(3))}")
        elif s.startswith("#"):
            close()
            n = len(s) - len(s.lstrip("#"))
            body.append(f"<h{n}>{inline(s[n:].strip())}</h{n}>")
        elif s and stack:
            body.append(" " + inline(s))
        elif s:
            body.append(f"<p>{inline(s)}</p>")
        i += 1
    close()
    title = re.sub(r"^#\s*", "", md.splitlines()[0])
    return (f"<!doctype html><html><head><meta charset='utf-8'><title>{html.escape(title)}</title>"
            f"<style>{CSS}</style></head><body>{''.join(body)}</body></html>")


def main():
    max_pages = int(sys.argv[sys.argv.index("--max-pages") + 1]) if "--max-pages" in sys.argv else 3
    browser = next((b for b in BROWSERS if os.path.exists(b)), None)
    if not browser:
        sys.exit("No Edge or Chrome found for headless printing.")
    md = SRC.read_text(encoding="utf-8")
    page = to_html(md)
    n_tables_md = len(re.findall(r"^\s*\|---", md, flags=re.M))
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "report.html"
        src.write_text(page, encoding="utf-8")
        OUT.parent.mkdir(exist_ok=True)
        subprocess.run([browser, "--headless", "--disable-gpu", "--no-pdf-header-footer",
                        f"--print-to-pdf={OUT}", src.as_uri()], check=True, capture_output=True, timeout=120)
    pdf = OUT.read_bytes()
    pages = len(re.findall(rb"/Type\s*/Page[^s]", pdf))
    checks = {
        f"pages <= {max_pages}": pages <= max_pages,
        "A4 page size": bool(re.search(rb"/MediaBox\s*\[0 0 59[45]\.\d+ 84[12]\.\d+\]", pdf)),
        f"{n_tables_md} tables in report.md rendered as HTML tables": page.count("<table>") == n_tables_md,
        "no local file paths or link targets in the PDF": not re.search(rb"file:|/URI|Users[\\/]", pdf),
    }
    words = len(html.unescape(re.sub(r"<[^>]+>", " ", page.split("<body>", 1)[1])).split())
    print(f"wrote {OUT.relative_to(ROOT)}: {pages} pages, {words} rendered words, {len(pdf):,} bytes")
    for k, v in checks.items():
        print(f"  [{'PASS' if v else 'FAIL'}] {k}")
    if not all(checks.values()):
        sys.exit(1)


if __name__ == "__main__":
    main()
