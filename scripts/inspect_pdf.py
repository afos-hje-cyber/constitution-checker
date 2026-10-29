"""Inspect the Constitution PDF before writing the parser.

Run:  .venv\\Scripts\\python scripts\\inspect_pdf.py

Key layout fact found while inspecting: every PDF page is a landscape
"2-up spread" (two printed pages side by side), rotated 90 degrees.
In pymupdf page coordinates that means:
  - x grows as you read down the printed page (line order),
  - y separates the two printed pages: y > MID_Y is the LEFT printed page,
    y < MID_Y is the RIGHT printed page.
pymupdf's default text order puts the right page first, so we also build a
reading-order version (left page, then right page, each sorted by x).

Outputs (nothing here builds the final dataset):
  data/interim/raw_text.txt          default pymupdf order
  data/interim/raw_text_ordered.txt  reading order (used for the report)
"""

import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from common import config  # noqa: E402

PDF_PATH = config.PDF_PATH
RAW_PATH = config.INTERIM_DIR / "raw_text.txt"
ORDERED_PATH = config.INTERIM_DIR / "raw_text_ordered.txt"

MID_Y = 298          # half of the page height (596 pt): boundary between printed pages
FIRST_BODY_PAGE = 9  # pages 1-8 are cover, title, index and colophon


# ---------------------------------------------------------------- extraction

def extract_raw(doc):
    """Default pymupdf text, one string per page."""
    return [page.get_text() for page in doc]


def extract_ordered(doc):
    """Text in reading order, one string per page.

    Blocks spanning both halves (the running header) go first, then the left
    printed page, then the right one. Inside each half blocks are sorted by x.
    """
    pages = []
    for page in doc:
        spanning, left, right = [], [], []
        for x0, y0, x1, y1, text, *_ in page.get_text("blocks"):
            if y0 < MID_Y < y1:
                spanning.append((x0, text))
            elif y0 >= MID_Y:
                left.append((x0, text))
            else:
                right.append((x0, text))
        parts = []
        for name, blocks in (("SPAN", spanning), ("LEFT", left), ("RIGHT", right)):
            if blocks:
                parts.append(f"--- {name} ---\n")
                parts.extend(text for _, text in sorted(blocks))
        pages.append("".join(parts))
    return pages


def save_pages(pages, out_path):
    """Write all pages to one file with '=== PAGE n ===' markers."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for i, text in enumerate(pages, start=1):
            f.write(f"=== PAGE {i} ===\n")
            f.write(text if text.endswith("\n") or not text else text + "\n")


def body_lines(pages):
    """(page_number, line) for every body line, page markers excluded."""
    out = []
    for p, text in enumerate(pages, start=1):
        if p < FIRST_BODY_PAGE:
            continue
        for ln in text.splitlines():
            if not ln.startswith("--- "):
                out.append((p, ln))
    return out


# ------------------------------------------------------------------- reports

def section(title):
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


def report_basics(doc, pages):
    section("1-2. BASICS")
    print(f"PDF pages: {len(doc)}   page size: {doc[0].rect}")
    dirs = Counter()
    for page in doc:
        for b in page.get_text("dict")["blocks"]:
            for line in b.get("lines", []):
                dirs[tuple(round(v) for v in line["dir"])] += 1
    print(f"Text line directions (all pages): {dict(dirs)}")
    print("Edition lines found:")
    for p, text in enumerate(pages[:FIRST_BODY_PAGE], start=1):
        for ln in text.splitlines():
            if re.search(r"revis|publica|isbn|lisboa|di[aá]rio", ln, re.I):
                print(f"  p{p}: {ln.strip()}")


def report_repeated(pages):
    """Lines repeated across pages, with digits normalised to '#'
    so that '18 | CONSTITUIÇÃO...' and '20 | CONSTITUIÇÃO...' count as one."""
    section("4. REPEATED LINES (digits -> #, body pages, >= 4 pages)")
    counter = Counter()
    for p, text in enumerate(pages, start=1):
        if p < FIRST_BODY_PAGE:
            continue
        shapes = {re.sub(r"\d+", "#", ln.strip()) for ln in text.splitlines()
                  if ln.strip() and not ln.startswith("--- ")}
        counter.update(shapes)
    for shape, n in counter.most_common():
        if n >= 4:
            print(f"  {n:4d}  {shape!r}")


HEADING_RES = {
    "Preâmbulo": r"^\s*PRE[AÂ]MBULO\b",
    "Princípios fundamentais": r"^\s*PR[IÍ]NC[IÍ]PIOS FUNDAMENTAIS\s*$",
    "PARTE": r"^\s*PARTE\b",
    "TÍTULO": r"^\s*T[IÍ]TULO\b",
    "CAPÍTULO": r"^\s*CAP[IÍ]TULO\b",
    "SECÇÃO": r"^\s*SEC[CÇ][AÃ]O\b",
    "Artigo": r"^\s*ARTIGOS?\b",
}


def shape_of(line):
    """Abstract a heading line: numbers -> N, roman numerals -> R."""
    s = re.sub(r"\d+", "N", line.strip())
    return re.sub(r"\b[IVXL]+\b", "R", s)


def report_headings(lines):
    section("5. STRUCTURAL HEADING PATTERNS (body pages)")
    for name, rx in HEADING_RES.items():
        groups = defaultdict(list)
        for i, (p, ln) in enumerate(lines):
            if re.match(rx, ln, re.I):
                nxt = lines[i + 1][1].strip() if i + 1 < len(lines) else ""
                groups[shape_of(ln)].append((p, ln.strip(), nxt))
        print(f"\n[{name}]  {sum(len(v) for v in groups.values())} lines")
        for shape, items in sorted(groups.items(), key=lambda kv: -len(kv[1])):
            print(f"  shape {shape!r}: {len(items)}")
            for p, ln, nxt in items[:3]:
                print(f"      p{p}: {ln!r}  -> next: {nxt!r}")


def report_paragraphs(lines):
    section("6. NUMBERED PARAGRAPHS AND ALÍNEAS")
    para = [(p, ln) for p, ln in lines if re.match(r"^\s*\d+\.\s", ln)]
    alin = [(p, ln) for p, ln in lines if re.match(r"^\s*[a-z]{1,2}\)\s", ln)]
    print(f"Lines starting with 'N. ': {len(para)}")
    spaces = Counter(re.match(r"^\s*\d+\.(\s+)", ln).group(1) for _, ln in para)
    print(f"  spacing after 'N.': {dict(spaces)}")
    print(f"Lines starting with 'x) ': {len(alin)}")
    letters = Counter(re.match(r"^\s*([a-z]{1,2})\)", ln).group(1) for _, ln in alin)
    print(f"  letters used: {sorted(letters, key=lambda s: (len(s), s))}")


def report_hyphens_and_refs(lines):
    section("7. HYPHENATED LINE BREAKS AND IN-TEXT REFERENCES")
    soft = hard = 0
    soft_ex, hard_ex = [], []
    for (p, a), (_, b) in zip(lines, lines[1:]):
        a_s = a.rstrip()
        if re.search(r"\w-$", a_s):
            # next line starts lowercase -> word split; else a real hyphen
            if re.match(r"\s*[a-záéíóúâêôãõç]", b):
                soft += 1
                soft_ex.append((p, a_s[-30:], b.strip()[:30]))
            else:
                hard += 1
                hard_ex.append((p, a_s[-30:], b.strip()[:30]))
    print(f"Lines ending in '-': {soft + hard}  (next line lowercase: {soft}, other: {hard})")
    for p, a, b in soft_ex[:5]:
        print(f"  p{p}: ...{a!r} + {b!r}")
    print("  'other' examples:")
    for p, a, b in hard_ex[:5]:
        print(f"  p{p}: ...{a!r} + {b!r}")

    refs = [(p, ln) for p, ln in lines
            if re.search(r"\bartigos?\s+\d+", ln) and not re.match(r"^\s*ARTIGO", ln)]
    print(f"\nLines with in-text 'artigo(s) N' references: {len(refs)}")
    starts = [(p, ln) for p, ln in refs if re.match(r"^\s*artigos?\s+\d+", ln, re.I)]
    print(f"  of which the reference is at line start: {len(starts)}")
    for p, ln in starts[:5]:
        print(f"    p{p}: {ln.strip()!r}")


# Strict body heading: the whole line is "ARTIGO N.º" (optionally with spaces).
STRICT_ARTICLE_RE = re.compile(r"^\s*ARTIGO\s+(\d+)\.º\s*$")
# Loose candidate: any line starting with Artigo + number, any case/symbol.
LOOSE_ARTICLE_RE = re.compile(r"^\s*ARTIGOS?\s+(\d+)", re.I)


def report_article_count(lines):
    section("8. ARTICLE HEADING COUNT (body pages)")
    strict = [(p, ln, int(m.group(1))) for p, ln in lines
              if (m := STRICT_ARTICLE_RE.match(ln))]
    loose = [(p, ln) for p, ln in lines if LOOSE_ARTICLE_RE.match(ln)]
    nums = [n for _, _, n in strict]
    print(f"Strict matches: {len(strict)}   distinct: {len(set(nums))}")
    print(f"  missing 1..296: {sorted(set(range(1, 297)) - set(nums))}")
    print(f"  duplicates: {sorted(n for n, c in Counter(nums).items() if c > 1)}")
    print(f"  out of order: {[(a, b) for a, b in zip(nums, nums[1:]) if b != a + 1]}")
    rejected = [(p, ln) for p, ln in loose if not STRICT_ARTICLE_RE.match(ln)]
    print(f"Loose matches rejected by strict regex: {len(rejected)}")
    for shape, n in Counter(shape_of(ln) for _, ln in rejected).most_common():
        print(f"  {n:4d}  {shape!r}")


def main():
    with pymupdf.open(PDF_PATH) as doc:
        raw = extract_raw(doc)
        ordered = extract_ordered(doc)
        save_pages(raw, RAW_PATH)
        save_pages(ordered, ORDERED_PATH)
        print(f"Saved {RAW_PATH} and {ORDERED_PATH}")
        report_basics(doc, raw)

    lines = body_lines(ordered)
    report_repeated(ordered)
    report_headings(lines)
    report_paragraphs(lines)
    report_hyphens_and_refs(lines)
    report_article_count(lines)


if __name__ == "__main__":
    main()
