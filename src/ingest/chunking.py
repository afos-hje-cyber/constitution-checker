"""Turn parsed articles into chunks for embedding.

Three strategies:
  "article"   one chunk per article (full_text)
  "paragraph" one chunk per numbered paragraph (articles without numbered
              paragraphs stay as one chunk)
  "hybrid"    whole article if it is short, split by paragraph if it is long

In "paragraph" and "hybrid", a chunk that is still over the model's token
limit (e.g. a long list of alíneas) is split at alínea boundaries; every part
repeats the paragraph's introduction. "article" is never split further: it is the
baseline, and its over-long chunks are recorded as truncated at build time.

Every chunk text starts with a context prefix so that a paragraph read on its
own still says where it comes from. Two prefix versions exist:
  "v1_basic" (default)  "Artigo 123.º, n.º 1 — Reelegibilidade: ..."
  "v2_hierarchy"        "Artigo 123.º, n.º 1 — Presidente da República ›
                         Estatuto e eleição › Reelegibilidade: ..."
v2 scored worse in the retrieval test (see eval/NOTES.md) and is kept only so
the experiment can be reproduced. The Preâmbulo is always one chunk.
"""

import json
import re
from common import config

ARTICLES_PATH = config.PROCESSED_DIR / "articles.json"
STRATEGIES = ("article", "paragraph", "hybrid")
DEFAULT_MAX_WORDS = 200   # hybrid threshold, counted on the article text
MAX_TOKENS = 512          # model limit: chunks above this get an alínea split
TARGET_TOKENS = 400       # size of each part after an alínea split

ALINEA_RE = re.compile(r"^([a-z]{1,2})\)")

# Recorded in the index metadata; add a new version whenever the prefix changes.
PREFIX_VERSIONS = ("v1_basic", "v2_hierarchy")
DEFAULT_PREFIX_VERSION = "v1_basic"

# Words that keep a capital letter when an UPPERCASE title is sentence-cased.
PROPER_NOUNS = {
    "república": "República",
    "constituição": "Constituição",
    "tribunal constitucional": "Tribunal Constitucional",
}


def sentence_case(title):
    """'PRESIDENTE DA REPÚBLICA' -> 'Presidente da República'.
    Titles that are already mixed case are returned unchanged."""
    if not title.isupper():
        return title
    text = title.lower()
    for lower, proper in PROPER_NOUNS.items():
        text = re.sub(rf"\b{lower}\b", proper, text)
    return text[0].upper() + text[1:]


def hierarchy(article):
    """The two most specific levels among part › título › capítulo."""
    levels = [article["part_title"], article["titulo_title"], article["capitulo_title"]]
    present = [sentence_case(t) for t in levels if t]
    return " › ".join(present[-2:])


def word_count(text):
    return len(text.split())


def estimate_tokens(text):
    """Rough token count when no tokenizer is given (e5: ~1.43 tokens/word)."""
    return int(word_count(text) * 1.5)


def label(article, n=None, alineas=None):
    """Human-readable citation, e.g. 'Artigo 227.º, n.º 1, alíneas a) a l)'."""
    if article["number"] is None:
        return "Preâmbulo"
    text = f"Artigo {article['number']}.º"
    if n is not None:
        text += f", n.º {n}"
    if alineas:
        first, last = alineas
        text += f", alíneas {first}) a {last})" if first != last else f", alínea {first})"
    return text


def make_prefix(article, n, alineas, prefix_version):
    if article["number"] is None:
        return "Preâmbulo: "
    if prefix_version == "v1_basic":
        return f"{label(article, n, alineas)} — {article['title']}: "
    if prefix_version == "v2_hierarchy":
        return f"{label(article, n, alineas)} — {hierarchy(article)} › {article['title']}: "
    raise ValueError(f"unknown prefix_version {prefix_version!r}, expected {PREFIX_VERSIONS}")


def make_chunk(article, text, n, strategy, prefix_version, alineas=None):
    """alineas: (first, last) letters when the chunk is part of a split paragraph."""
    prefix = make_prefix(article, n, alineas, prefix_version)
    if article["number"] is None:
        chunk_id = "preambulo"
    else:
        chunk_id = f"art{article['number']}" + (f"_n{n}" if n is not None else "")
        if alineas:
            chunk_id += f"_{alineas[0]}-{alineas[1]}"
    return {
        "chunk_id": chunk_id,
        "article": article["number"],
        "paragraph": n,
        "alineas": f"{alineas[0]}-{alineas[1]}" if alineas else None,
        "title": article["title"],
        "part_title": article["part_title"],
        "strategy": strategy,
        "text": prefix + text,
    }


def split_by_alinea(article, text, n, strategy, length_fn, prefix_version):
    """Split one paragraph if its chunk is over MAX_TOKENS.

    The text looks like "intro\\na) ...\\nb) ...". Each part is the intro plus
    a run of consecutive alíneas, filled up to ~TARGET_TOKENS. Returns one
    chunk if no split is needed (or possible).
    """
    whole = make_chunk(article, text, n, strategy, prefix_version)
    lines = text.split("\n")
    intro_lines = []
    while lines and not ALINEA_RE.match(lines[0]):
        intro_lines.append(lines.pop(0))
    if length_fn(whole["text"]) <= MAX_TOKENS or len(lines) < 2:
        return [whole]

    def part(group):
        letters = [ALINEA_RE.match(ln).group(1) for ln in group if ALINEA_RE.match(ln)]
        return make_chunk(article, "\n".join(intro_lines + group), n, strategy,
                          prefix_version, (letters[0], letters[-1]))

    # Greedily group alíneas (a trailing non-alínea line stays with the last group).
    groups, current = [], []
    for line in lines:
        if current and ALINEA_RE.match(line) and \
                length_fn(part(current + [line])["text"]) > TARGET_TOKENS:
            groups.append(current)
            current = [line]
        else:
            current.append(line)
    groups.append(current)
    return [part(g) for g in groups]


def split_by_paragraph(article, strategy, length_fn, prefix_version):
    """One chunk per numbered paragraph; unnumbered articles stay whole.
    Chunks that are still over the token limit are split by alínea."""
    paragraphs = article["paragraphs"]
    if all(p["n"] is None for p in paragraphs):
        return split_by_alinea(article, article["full_text"], None, strategy,
                               length_fn, prefix_version)
    chunks = []
    for p in paragraphs:
        chunks.extend(split_by_alinea(article, p["text"], p["n"], strategy,
                                      length_fn, prefix_version))
    return chunks


def make_chunks(articles, strategy, max_words=DEFAULT_MAX_WORDS, length_fn=estimate_tokens,
                prefix_version=DEFAULT_PREFIX_VERSION):
    """Return a list of chunk dicts for the given strategy.

    max_words: "hybrid" only; articles with more words are split by paragraph.
    length_fn: counts the tokens of a chunk text; used by the alínea split in
               "paragraph" and "hybrid". Pass the real tokenizer when building
               the index; the default is a word-based estimate.
    prefix_version: "v1_basic" (default) or "v2_hierarchy".
    """
    if strategy not in STRATEGIES:
        raise ValueError(f"unknown strategy {strategy!r}, expected one of {STRATEGIES}")

    chunks = []
    for article in articles:
        whole = make_chunk(article, article["full_text"], None, strategy, prefix_version)
        if article["number"] is None or strategy == "article":
            chunks.append(whole)
        elif strategy == "paragraph":
            chunks.extend(split_by_paragraph(article, strategy, length_fn, prefix_version))
        elif word_count(article["full_text"]) <= max_words:   # hybrid, short
            chunks.append(whole)
        else:                                                  # hybrid, long
            chunks.extend(split_by_paragraph(article, strategy, length_fn, prefix_version))
    return chunks


def load_articles(path=ARTICLES_PATH):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


if __name__ == "__main__":
    # Quick sanity check: chunk counts and one example per strategy.
    articles = load_articles()
    for s in STRATEGIES:
        chunks = make_chunks(articles, s)
        ids = [c["chunk_id"] for c in chunks]
        assert len(ids) == len(set(ids)), "duplicate chunk ids"
        example = next(c for c in chunks if c["article"] == 24)
        print(f"{s:10s} {len(chunks):5d} chunks   e.g. {example['text'][:70]!r}")
