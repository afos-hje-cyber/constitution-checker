"""Parse the Constitution PDF into one JSON record per article.

Run:  .venv\\Scripts\\python scripts\\parse_constitution.py

Pipeline (rule numbers refer to the approved inspection rules):
  1. Extract text in reading order (each PDF page = two book pages, rotated).
  2-6. Keep body pages, drop running headers/footers/blank lines, fix ligatures.
  7-15. Walk the lines with a small state machine: structure headings,
        article headings + titles, numbered paragraphs, alíneas.
  16. Keep text as printed; suspected typos are only listed.
  17. Validate the result and print a report.

Outputs:
  data/processed/articles.json   one record per article (+ Preâmbulo)
  data/interim/hyphen_joins.txt  every hyphen join made while rebuilding text
  data/interim/typos.txt         suspected typos in the source (not corrected)
"""

import json
import re
from collections import Counter
import pymupdf

from common import config

PDF_PATH = config.PDF_PATH
OUT_PATH = config.PROCESSED_DIR / "articles.json"
HYPHEN_LOG = config.INTERIM_DIR / "hyphen_joins.txt"
TYPO_LOG = config.INTERIM_DIR / "typos.txt"

MID_Y = 298            # half of the page height: boundary between the two book pages
FIRST_BODY_PAGE = 9    # pages 1-8: cover, title, index, colophon
INDEX_PAGES = range(3, 9)

# Private-use characters the PDF font uses for ligatures.
LIGATURES = {"": "fi", "": "fl"}

# Noise lines (rules 3-4).
HEADER_RIGHT_RE = re.compile(r"^(.+?)\s+\|\s+\d+$")       # "ORGANIZAÇÃO ECONÓMICA   |  61"
HEADER_LEFT_RE = re.compile(r"^\d+\s+\|\s+CONSTITUIÇÃO DA REPÚBLICA PORTUGUESA$")
FOOTER_RE = re.compile(r"^ARTIGOS \d+\.º/\d+\.º$")        # "ARTIGOS 1.º/7.º"

# Structure (rules 8, 11, 12). All case-sensitive on purpose: in-text
# references are lowercase ("artigo 18.º") and must never become headings.
ARTICLE_RE = re.compile(r"^ARTIGO (\d+)\.º$")
PART_RE = re.compile(r"^PARTE ([IVX]+)$")
TITULO_RE = re.compile(r"^TÍTULO ([IVX]+)$")
CAPITULO_RE = re.compile(r"^CAPÍTULO ([IVX]+)$")
UNNUMBERED_PARTS = {"PRINCÍPIOS FUNDAMENTAIS", "DISPOSIÇÕES FINAIS E TRANSITÓRIAS"}
PREAMBLE = "PREÂMBULO"

# Paragraphs and alíneas (rules 13-14).
PARA_RE = re.compile(r"^(\d+)\.\s+(.*)$")                  # "1.  Texto..."
# "a)  Texto" (two spaces) or "a) Texto" (capital letter). Rejects the wrapped
# reference "b) do n.º 1 do artigo 227.º;".
ALINEA_RE = re.compile(r"^[a-z]{1,2}\)(\s{2,}|\s+(?=[A-ZÀ-Ý]))")


# --------------------------------------------------------------- rule 1

def reading_order_lines(page):
    """Return the text lines of one PDF page in reading order.

    Each PDF page holds two book pages turned 90 degrees, so every printed
    line runs vertically: its position along x says WHICH LINE it is, and its
    position along y says WHICH BOOK PAGE it is on (y > MID_Y = left page).
    So we group blocks by y (left page, then right page) and sort each group
    by x. The running header spans both halves and goes first.
    """
    spanning, left, right = [], [], []
    for x0, y0, x1, y1, text, *_ in page.get_text("blocks"):
        if y0 < MID_Y < y1:
            spanning.append((x0, text))
        elif y0 >= MID_Y:
            left.append((x0, text))
        else:
            right.append((x0, text))
    lines = []
    for group in (spanning, left, right):
        for _, text in sorted(group):
            lines.extend(text.splitlines())
    return lines


def fix_ligatures(text):
    for char, letters in LIGATURES.items():
        text = text.replace(char, letters)
    return text


# ------------------------------------------------------------ rules 2-6

def clean_body_lines(doc, stats):
    """(page, line) for every body line, with noise removed.

    `stats` collects how many lines each rule removed (checked in rule 17)
    and the section names seen in the running headers (for the typo list).
    """
    out = []
    for page_no in range(FIRST_BODY_PAGE, len(doc) + 1):
        for raw in reading_order_lines(doc[page_no - 1]):
            line = fix_ligatures(raw).strip()
            if not line:
                stats["blank"] += 1
            elif HEADER_LEFT_RE.match(line):
                stats["header_left"] += 1
            elif m := HEADER_RIGHT_RE.match(line):
                stats["header_right"] += 1
                stats["header_names"].add(m.group(1))
            elif FOOTER_RE.match(line):
                stats["footer"] += 1
            else:
                out.append((page_no, line))
    return out


# --------------------------------------------------------------- rule 7

WORD_RE = re.compile(r"\w+(?:-\w+)*")


def bare(word):
    """Lowercase word without surrounding punctuation: 'cialista,' -> 'cialista'."""
    return re.sub(r"^\W+|\W+$", "", word).lower()


def build_vocab(lines):
    """Count words that are NOT broken across a line end.

    Used to decide ambiguous hyphen breaks: the last word of a line ending in
    '-' and the first word of the following line are left out.
    """
    vocab = Counter()
    for k, (_, line) in enumerate(lines):
        words = line.split()
        if line.endswith("-"):
            words = words[:-1]
        if k > 0 and lines[k - 1][1].endswith("-"):
            words = words[1:]
        vocab.update(w.lower() for w in WORD_RE.findall(" ".join(words)))
    return vocab


def join_lines(pieces, hyphen_log, vocab):
    """Join wrapped lines [(page, text), ...] into one string.

    - "Vice-" + "-Presidentes" -> "Vice-Presidentes" (hyphen belongs to the word)
    - "re-" + "sistência"      -> "resistência"      (word split at line end)
    - "faz-" + "se"            -> "faz-se" only when "fazse" never appears in
      the text but "faz-se" does (a hyphenated word broken at its own hyphen)
    - otherwise lines are joined with a space.
    Every hyphen join is appended to `hyphen_log`.
    """
    prev_page, text = pieces[0]
    for page, nxt in pieces[1:]:
        if text.endswith("-"):
            left = text.split()[-1]
            right = nxt.split()[0]
            joined, hyphenated = bare(left[:-1] + right), bare(left + right)
            if nxt.startswith("-"):
                word = left + right[1:]
                text = text + nxt[1:]
            elif vocab[joined] == 0 and vocab[hyphenated] > 0:
                word = left + right
                text = text + nxt
            else:
                word = left[:-1] + right
                text = text[:-1] + nxt
            hyphen_log.append({"page": prev_page, "left": left, "right": right,
                               "word": re.sub(r"^\W+|\W+$", "", word)})
        else:
            text = text + " " + nxt
        prev_page = page
    return re.sub(r"\s+", " ", text).strip()   # collapse "1.  Texto" double spaces


# ----------------------------------------------------------- rules 8-15

def new_record(number, title, state):
    return {"number": number, "title": title, **state, "paragraphs": []}


def parse(lines, hyphen_log, warnings):
    """Turn cleaned (page, line) pairs into a list of article records."""
    vocab = build_vocab(lines)
    records = []
    state = {"part": None, "part_title": None, "titulo": None,
             "titulo_title": None, "capitulo": None, "capitulo_title": None}
    record = None      # article being filled
    para = None        # {"n": int|None, "segments": [[(page, line), ...], ...]}
    expected_n = 1     # next numbered paragraph expected in this article

    def heading_title(i, label):
        """Structure titles take one line; the line after must be a heading."""
        after = lines[i + 2][1] if i + 2 < len(lines) else ""
        if not (ARTICLE_RE.match(after) or TITULO_RE.match(after)
                or CAPITULO_RE.match(after)):
            warnings.append(f"{label}: line after title is not a heading: {after!r}")
        return lines[i + 1][1]

    i = 0
    while i < len(lines):
        page, line = lines[i]

        if line == PREAMBLE:
            record = new_record(None, "Preâmbulo", state)
            records.append(record)
            para, expected_n = None, 1

        elif line in UNNUMBERED_PARTS:
            state.update(part=None, part_title=line, titulo=None,
                         titulo_title=None, capitulo=None, capitulo_title=None)
            record = None

        elif m := PART_RE.match(line):
            state.update(part=m.group(1), part_title=heading_title(i, line),
                         titulo=None, titulo_title=None,
                         capitulo=None, capitulo_title=None)
            record = None
            i += 1

        elif m := TITULO_RE.match(line):
            state.update(titulo=m.group(1), titulo_title=heading_title(i, line),
                         capitulo=None, capitulo_title=None)
            record = None
            i += 1

        elif m := CAPITULO_RE.match(line):
            state.update(capitulo=m.group(1), capitulo_title=heading_title(i, line))
            record = None
            i += 1

        elif m := ARTICLE_RE.match(line):
            number = int(m.group(1))
            next_line = lines[i + 1][1] if i + 1 < len(lines) else ""
            if record and record["number"] == number and not next_line.startswith("("):
                # Rule 10: repeated heading where an article continues on the
                # next book page (Art. 276.º). Keep filling the same article.
                pass
            else:
                # Rule 9: title runs from "(" to the line ending in ")".
                title_pieces = []
                while True:
                    i += 1
                    title_pieces.append(lines[i])
                    if lines[i][1].endswith(")") or len(title_pieces) == 3:
                        break
                title = join_lines(title_pieces, hyphen_log, vocab)
                if not (title.startswith("(") and title.endswith(")")):
                    warnings.append(f"Art. {number}: odd title {title!r}")
                record = new_record(number, title.strip("()").strip(), state)
                records.append(record)
                para, expected_n = None, 1

        else:
            # Body text of the current article.
            if record is None:
                warnings.append(f"p{page}: line outside any article: {line!r}")
            elif (m := PARA_RE.match(line)) and int(m.group(1)) == expected_n:
                para = {"n": expected_n, "segments": [[(page, m.group(2))]]}
                record["paragraphs"].append(para)
                expected_n += 1
            elif para is None:
                para = {"n": None, "segments": [[(page, line)]]}
                record["paragraphs"].append(para)
            elif ALINEA_RE.match(line):
                para["segments"].append([(page, line)])   # alínea starts a new line
            else:
                para["segments"][-1].append((page, line))
        i += 1

    # Rule 15: build the final strings. Inside a paragraph, alíneas keep a
    # line break; wrapped lines are joined with spaces.
    for rec in records:
        rec["paragraphs"] = [
            {"n": p["n"],
             "text": "\n".join(join_lines(seg, hyphen_log, vocab) for seg in p["segments"])}
            for p in rec["paragraphs"]
        ]
        rec["full_text"] = "\n".join(
            f"{p['n']}. {p['text']}" if p["n"] else p["text"] for p in rec["paragraphs"]
        )
    return records


# ------------------------------------------------- rule 7 log, rule 16 typos

def write_hyphen_log(hyphen_log, records):
    """Log every join and flag words never seen unhyphenated elsewhere."""
    vocab = Counter()
    for rec in records:
        vocab.update(w.lower() for w in WORD_RE.findall(rec["title"] + " " + rec["full_text"]))
    made_by_join = Counter(h["word"].lower() for h in hyphen_log)

    flagged = 0
    rows = []
    for h in hyphen_log:
        w = h["word"].lower()
        # The word appears elsewhere only if it occurs more often than our joins produced it.
        rare = vocab[w] <= made_by_join[w]
        flagged += rare
        flag = "  [FLAG: not found elsewhere unhyphenated]" if rare else ""
        rows.append(f"p{h['page']}\t{h['left']} | {h['right']}\t-> {h['word']}{flag}")

    HYPHEN_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(HYPHEN_LOG, "w", encoding="utf-8") as f:
        f.write(f"# {len(hyphen_log)} hyphen joins, {flagged} flagged\n")
        f.write("# page\tleft | right\t-> result\n")
        f.write("\n".join(rows) + "\n")
    return flagged


def index_titles(doc):
    """{article number: title} from the index pages, for cross-checking."""
    titles = {}
    for page_no in INDEX_PAGES:
        for line in fix_ligatures(doc[page_no - 1].get_text()).splitlines():
            m = re.match(r"^ARTIGO\s+(\d+)\.?º?\s*–\s*\((.+)\)\s*$", line.strip())
            if m:
                titles[int(m.group(1))] = m.group(2)
    return titles


def write_typos(records, doc, header_names):
    """List suspected typos in the source. Nothing is corrected."""
    found = []
    for rec in records:
        where = f"Art. {rec['number']}.º" if rec["number"] else "Preâmbulo"
        text = rec["title"] + "\n" + rec["full_text"]
        # Letter l or O inside a number, e.g. "l974".
        for m in re.finditer(r"\b(?:[lO]\d{2,}|\d+[lO]\d*)\b", text):
            found.append(f"{where}\tletter inside number\t{m.group(0)!r}")
        # Same word twice in a row, e.g. "de de" (but not "alíneas d) e e)").
        for m in re.finditer(r"\b(\w+)\s+\1\b(?!\))", text, re.IGNORECASE):
            found.append(f"{where}\trepeated word\t{m.group(0)!r}")

    # Article titles: index vs body.
    idx = index_titles(doc)
    for rec in records:
        n = rec["number"]
        if n in idx and idx[n] != rec["title"]:
            found.append(f"Art. {n}.º\tindex/body title differ\t"
                         f"index={idx[n]!r} body={rec['title']!r}")

    # Running-header section names that match no structural heading.
    known = {rec["part_title"] for rec in records if rec["part_title"]} | {PREAMBLE}
    for name in sorted(header_names - known):
        found.append(f"running header\tunknown section name\t{name!r}")

    with open(TYPO_LOG, "w", encoding="utf-8") as f:
        f.write(f"# {len(found)} suspected typos (NOT corrected in articles.json)\n")
        f.write(f"# index titles compared: {len(idx)}\n")
        f.write("\n".join(found) + "\n")
    return found


# -------------------------------------------------------------- rule 17

def validate(records, stats, warnings):
    """Print PASS/FAIL for each check. Returns True if all pass."""
    results = []

    def check(name, ok, detail=""):
        results.append(ok)
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}{'  ' + detail if detail else ''}")

    articles = [r for r in records if r["number"] is not None]
    numbers = [r["number"] for r in articles]
    preamble = [r for r in records if r["number"] is None]

    print("\nRule 17 validation")
    check("noise removed: 70 right headers, 69 left headers, 68 footers",
          (stats["header_right"], stats["header_left"], stats["footer"]) == (70, 69, 68),
          f"got {stats['header_right']}, {stats['header_left']}, {stats['footer']}")
    check("exactly 1 Preâmbulo with text", len(preamble) == 1 and bool(preamble[0]["full_text"]))
    check("296 articles numbered 1..296 in order", numbers == list(range(1, 297)),
          f"got {len(numbers)}")
    check("every article has a title", all(r["title"] for r in articles))
    check("every article has text", all(r["full_text"] for r in articles))

    bad_seq = [r["number"] for r in articles
               if [p["n"] for p in r["paragraphs"]] not in
               ([None], list(range(1, len(r["paragraphs"]) + 1)))]
    check("paragraphs are [unnumbered] or 1..k", not bad_seq, f"bad: {bad_seq}")

    check("every article has a part_title", all(r["part_title"] for r in articles))

    noise = []
    for r in records:
        for ln in (r["title"] + "\n" + r["full_text"]).splitlines():
            if (HEADER_RIGHT_RE.match(ln) or HEADER_LEFT_RE.match(ln) or FOOTER_RE.search(ln)
                    or "" in ln or "" in ln or ln.rstrip().endswith("-")
                    or re.search(r"ARTIGOS? \d+\.º", ln)):
                noise.append((r["number"], ln[-60:]))
    check("no headers/footers/ligatures/line-final '-' or ARTIGO headings in text",
          not noise, f"{noise[:5]}")
    check("no parser warnings", not warnings, f"{warnings[:5]}")

    print("\nArticles per part:")
    for title, n in Counter(r["part_title"] for r in articles).items():
        print(f"  {n:4d}  {title}")
    return all(results)


def main():
    stats = {"blank": 0, "header_left": 0, "header_right": 0, "footer": 0,
             "header_names": set()}
    hyphen_log, warnings = [], []

    with pymupdf.open(PDF_PATH) as doc:
        lines = clean_body_lines(doc, stats)
        records = parse(lines, hyphen_log, warnings)
        flagged = write_hyphen_log(hyphen_log, records)
        typos = write_typos(records, doc, stats["header_names"])

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    print(f"Clean body lines: {len(lines)}   records: {len(records)} -> {OUT_PATH}")
    print(f"Hyphen joins: {len(hyphen_log)} ({flagged} flagged) -> {HYPHEN_LOG}")
    print(f"Suspected typos: {len(typos)} -> {TYPO_LOG}")
    validate(records, stats, warnings)


if __name__ == "__main__":
    main()
