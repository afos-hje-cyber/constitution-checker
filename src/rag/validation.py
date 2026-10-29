"""Validate an LLM assessment against the chunks that were actually retrieved.

Kept separate from assess.py so it can be unit-tested without the embedding
model or any API call. Nothing the LLM says is trusted:
  - citations of articles (or n.º) the model was not shown are rejected;
  - article references written in "summary"/"reasoning" are checked too:
    not retrieved -> rejected and the label is forced to "unclear";
    retrieved but not cited -> added to the citations automatically;
  - a label other than "unclear" needs at least one valid citation.
"""

import json
import re
from functools import lru_cache

from common import config
from ingest.chunking import load_articles

# "é inconstitucional", "seria constitucional", ... (a verdict the prompt forbids)
VERDICT_RE = re.compile(r"\b(é|seria|será|são|seriam)\s+(in)?constitucion(al|ais)\b", re.I)

# --- article references in free text ----------------------------------------
# "artigo 24.º", "Artigo 24.º", "art. 24.º", "arts. 24.º", "artigos 24.º, 25.º e 30.º",
# each number optionally followed by ", n.º 1".
_ART_NUM = r"\d+\.º(?:\s*,\s*n\.º\s*\d+)?"
LIST_REF_RE = re.compile(
    rf"\b(?:artigos?|arts?\.)\s+({_ART_NUM}(?:\s*(?:,|e)\s*{_ART_NUM})*)", re.I)
# "o n.º 3 do artigo 57.º"
N_OF_ART_RE = re.compile(r"\bn\.º\s*(\d+)\s+do\s+(?:artigo|art\.)\s+(\d+)\.º", re.I)
# bare "24.º, n.º 1"
BARE_REF_RE = re.compile(r"(?<![\w.])(\d+)\.º\s*,\s*n\.º\s*(\d+)")


def extract_references(text):
    """Return the set of (article, n or None) referenced in `text`."""
    refs = set()
    for m in LIST_REF_RE.finditer(text):
        for art, n in re.findall(r"(\d+)\.º(?:\s*,\s*n\.º\s*(\d+))?", m.group(1)):
            refs.add((int(art), int(n) if n else None))
    for n, art in N_OF_ART_RE.findall(text):
        refs.add((int(art), int(n)))
    for art, n in BARE_REF_RE.findall(text):
        refs.add((int(art), int(n)))
    # (24, None) adds nothing when (24, n) is also there
    return {(a, n) for a, n in refs if n is not None or not any(b == a and m for b, m in refs)}


# --- structure -------------------------------------------------------------

def check_structure(data):
    """Raise ValueError if the JSON does not follow the schema (triggers one retry)."""
    if data.get("label") not in config.LABELS:
        raise ValueError(f"invalid label {data.get('label')!r}")
    for field in ("summary", "reasoning"):
        if not isinstance(data.get(field), str) or not data[field].strip():
            raise ValueError(f"missing {field}")
    if not isinstance(data.get("citations"), list):
        raise ValueError("citations is not a list")
    for c in data["citations"]:
        if not isinstance(c, dict) or not isinstance(c.get("article"), int):
            raise ValueError(f"bad citation {c!r}")
        if c.get("n") is not None and not isinstance(c["n"], int):
            raise ValueError(f"bad citation n {c!r}")
    mi = data.get("missing_information")
    if mi is not None and not isinstance(mi, str):
        raise ValueError("missing_information must be text or null")


# --- what the model was shown --------------------------------------------------

@lru_cache(maxsize=1)
def existing_paragraphs():
    """article number -> set of paragraph numbers that exist in the Constitution."""
    return {a["number"]: {p["n"] for p in a["paragraphs"] if p["n"]}
            for a in load_articles() if a["number"] is not None}


def shown(hits):
    """article -> "all" (whole article shown) or the set of n.º shown."""
    seen = {}
    for h in hits:
        if h["article"] is None:
            continue
        if h["paragraph"] is None:
            seen[h["article"]] = "all"
        elif seen.get(h["article"]) != "all":
            seen.setdefault(h["article"], set()).add(h["paragraph"])
    return seen


def problem(article, n, seen):
    """Why (article, n) cannot be relied on, or None if it was shown."""
    if article not in seen:
        return "artigo não incluído nos excertos recuperados"
    if n is not None and n not in existing_paragraphs().get(article, set()):
        return f"o artigo {article}.º não tem n.º {n}"
    if n is not None and seen[article] != "all" and n not in seen[article]:
        return f"n.º {n} do artigo {article}.º não estava nos excertos"
    return None


# --- main entry point ----------------------------------------------------------

def validate_output(data, hits):
    """Check an LLM answer against the retrieved chunks.

    Returns (result, rejected_citations, rejected_references, notes). `data`
    is not modified.
    """
    result = json.loads(json.dumps(data))   # deep copy
    seen = shown(hits)
    notes = []

    # 1. Citations: keep only what the model was shown.
    valid, rejected_citations = [], []
    for c in result["citations"]:
        reason = problem(c["article"], c.get("n"), seen)
        if reason:
            rejected_citations.append({**c, "reason": reason})
        else:
            valid.append(c)
    if rejected_citations:
        notes.append(f"{len(rejected_citations)} citação(ões) rejeitada(s)")

    # 2. References written in the text.
    rejected_references = []
    refs = extract_references(result["summary"] + "\n" + result["reasoning"])
    for article, n in sorted(refs, key=lambda r: (r[0], r[1] or 0)):
        reason = problem(article, n, seen)
        if reason:
            rejected_references.append({"article": article, "n": n,
                                        "reason": "mentioned in text but not retrieved",
                                        "detail": reason})
            continue
        already = any(c["article"] == article and (n is None or c.get("n") == n)
                      for c in valid)
        if not already:
            valid.append({"article": article, "n": n, "alinea": None,
                          "explanation": "referido no raciocínio"})
            notes.append(f"citação acrescentada: artigo {article}.º"
                         + (f", n.º {n}" if n else "") + " (referido no texto)")
    result["citations"] = valid

    # 3. Label rules.
    if rejected_references and result["label"] != "unclear":
        notes.append(f"etiqueta '{result['label']}' alterada para 'unclear': o texto "
                     "refere artigos que não estavam nos excertos")
        result["label"] = "unclear"
    if result["label"] != "unclear" and not valid:
        notes.append(f"etiqueta '{result['label']}' alterada para 'unclear': "
                     "nenhuma citação válida")
        result["label"] = "unclear"

    # 4. Forbidden verdict wording (warning only).
    for field in ("summary", "reasoning"):
        if VERDICT_RE.search(result[field]):
            notes.append(f"possível veredicto proibido em '{field}'")

    return result, rejected_citations, rejected_references, notes
