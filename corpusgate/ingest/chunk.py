"""Structure-aware chunking: normalized text to chunks that honor the anchor contract.

Every chunk ID is DOCID#section-slug:ordinal, so a chunk carries its
gold-anchor section in its own name and retrieval scoring matches by
prefix. Contracts number themselves five different ways across this
corpus, and the detector handles each:

- preamble: everything before the first accepted structural heading
- decimal headings at line start (1.3, 14.3, 3.01) become their literal slug
- bare numbered headings at line start (1., 27.) become section-N,
  accepted only in monotonic order so restarting sub-lists inside a
  section do not fork phantom sections
- lettered parts with caps-only headings (A. AUTHORITY) open a letter
  context; numbered items inside become letter slugs like section-i.5,
  monotonic per letter with item matches taking priority while a
  letter part is open
- bare-number candidates come from line starts and inline positions in
  one merged stream, so contracts that flow their numbering mid-line
  chunk the same way as line-anchored ones; a one-item gap tolerance
  absorbs source noise such as malformed entities swallowing an item

Within a section, text splits into fixed-size chunks with overlap;
each chunk records its character span in the normalized text, so
provenance runs raw file to normalized span to chunk.
"""

import argparse
import json
import re
import sys
from pathlib import Path

DECIMAL_RE = re.compile(r"^(\d{1,2}\.\d{1,2})\.?\s+\S", re.M)
LETTER_RE = re.compile(r"^([A-Z])\.\s+([^\n]{2,70})$", re.M)
BARE_RE = re.compile(r"(?:^|(?<=[\n ]))(\d{1,2})\.\s+(?=[A-Z$\"(])")

MAX_CHARS = 1600
OVERLAP = 200


def _is_caps_heading(rest: str) -> bool:
    letters = [c for c in rest if c.isalpha()]
    if len(letters) < 3:
        return False
    return sum(c.isupper() for c in letters) / len(letters) > 0.9


def detect_sections(text: str) -> list[tuple[str, int]]:
    """Ordered (slug, char_offset) section starts; the preamble is implicit.

    Candidates from three shapes (line-anchored decimals, caps-only
    lettered parts, bare numbers at line starts or inline) merge into
    one offset-ordered stream, then a monotonic state machine accepts
    top-level numbers only in sequence and routes numbers inside an
    open lettered part to letter.item slugs. Sub-lists that restart at
    one, page furniture, and cross references all fail the monotonic
    test and never fork phantom sections.
    """
    candidates: list[tuple[int, str, object]] = []
    for m in DECIMAL_RE.finditer(text):
        candidates.append((m.start(), "decimal", m.group(1)))
    for m in LETTER_RE.finditer(text):
        if _is_caps_heading(m.group(2)):
            candidates.append((m.start(), "letter", m.group(1).lower()))
    for m in BARE_RE.finditer(text):
        candidates.append((m.start(1), "bare", int(m.group(1))))
    candidates.sort(key=lambda c: c[0])

    sections: list[tuple[str, int]] = []
    expected_top = 1
    letter: str | None = None
    expected_item = 1
    for offset, kind, value in candidates:
        if kind == "decimal":
            letter = None
            sections.append((f"section-{value}", offset))
        elif kind == "letter":
            letter = value
            expected_item = 1
            sections.append((f"section-{letter}", offset))
        elif kind == "bare":
            if letter is not None and expected_item <= value <= expected_item + 1:
                sections.append((f"section-{letter}.{value}", offset))
                expected_item = value + 1
            elif expected_top <= value <= expected_top + 1:
                letter = None
                sections.append((f"section-{value}", offset))
                expected_top = value + 1
    return sections


def chunk_section(slug: str, doc_id: str, text: str, base: int) -> list[dict]:  # noqa: D103
    chunks = []
    start = 0
    ordinal = 0
    while start < len(text):
        end = min(len(text), start + MAX_CHARS)
        piece = text[start:end].strip()
        if piece:
            chunks.append(
                {
                    "chunk_id": f"{doc_id}#{slug}:{ordinal}",
                    "doc_id": doc_id,
                    "section": slug,
                    "doc_title": "",
                    "text": piece,
                    "char_start": base + start,
                    "char_end": base + end,
                }
            )
            ordinal += 1
        if end == len(text):
            break
        start = end - OVERLAP
    return chunks


def doc_title(text: str, doc_id: str) -> str:
    """A short human title from the document head, for embedding context."""
    for line in text.split("\n")[:12]:
        if re.search(r"AGREEMENT|PLAN|LETTER|CONTRACT", line, re.I) and len(line) < 90:
            return line.strip()
    return doc_id


def chunk_document(normalized: dict) -> list[dict]:
    text = normalized["text"]
    doc_id = normalized["doc_id"]
    title = doc_title(text, doc_id)
    sections = detect_sections(text)
    spans: list[tuple[str, int, int]] = []
    first = sections[0][1] if sections else len(text)
    if first > 0:
        spans.append(("preamble", 0, first))
    for i, (slug, start) in enumerate(sections):
        end = sections[i + 1][1] if i + 1 < len(sections) else len(text)
        spans.append((slug, start, end))
    chunks = []
    next_ordinal: dict[str, int] = {}
    for slug, start, end in spans:
        section_chunks = chunk_section(slug, doc_id, text[start:end], start)
        base = next_ordinal.get(slug, 0)
        for i, c in enumerate(section_chunks):
            c["chunk_id"] = f"{doc_id}#{slug}:{base + i}"
            c["doc_title"] = title
        next_ordinal[slug] = base + len(section_chunks)
        chunks.extend(section_chunks)
    return chunks


def chunk_all(
    normalized_root: str | Path = "corpus/normalized",
    out_path: str | Path = "corpus/normalized/chunks.jsonl",
) -> dict:
    normalized_root = Path(normalized_root)
    all_chunks = []
    docs = 0
    for path in sorted(normalized_root.glob("*.json")):
        normalized = json.loads(path.read_text())
        all_chunks.extend(chunk_document(normalized))
        docs += 1
    with open(out_path, "w") as f:
        for chunk in all_chunks:
            f.write(json.dumps(chunk) + "\n")
    sections = len({(c["doc_id"], c["section"]) for c in all_chunks})
    return {"documents": docs, "sections": sections, "chunks": len(all_chunks)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--normalized", default="corpus/normalized")
    parser.add_argument("--out", default="corpus/normalized/chunks.jsonl")
    args = parser.parse_args(argv)
    stats = chunk_all(args.normalized, args.out)
    print(f"chunked {stats['documents']} documents into {stats['chunks']} chunks "
          f"across {stats['sections']} sections")
    return 0


if __name__ == "__main__":
    sys.exit(main())
