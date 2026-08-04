"""Parsers per source format: raw corpus bytes to normalized text with provenance.

One normalized document per manifest entry, written to
corpus/normalized/<doc_id>.json: cleaned text that preserves line
structure (the chunker's section detection is line-anchored), plus
the source path, the sha256 of the raw bytes, and the doc id, so
every chunk minted later traces to its document and character span.

Two parsers exist because the corpus has two formats: CUAD plain
text, which needs whitespace normalization without losing headings,
and EDGAR exhibit HTML, which needs tag stripping that preserves
block boundaries. Parsing is deterministic: same raw bytes, same
normalized text, forever.
"""

import argparse
import hashlib
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

from corpusgate.evals.schema import doc_id as derive_doc_id
from corpusgate.ingest.fetch import destination, load_manifest

BLOCK_TAGS = {"p", "div", "tr", "br", "table", "li", "h1", "h2", "h3", "h4"}


class _HTMLText(HTMLParser):
    """Tag stripper that keeps block boundaries as newlines."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in ("script", "style"):
            self._skip_depth += 1
        if tag in BLOCK_TAGS:
            self.parts.append("\n")
        if tag in ("td", "th"):
            self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style") and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            self.parts.append(data)


def parse_html(raw: str) -> str:
    parser = _HTMLText()
    parser.feed(raw)
    return normalize_text("".join(parser.parts))


def parse_txt(raw: str) -> str:
    return normalize_text(raw)


def normalize_text(text: str) -> str:
    """Collapse noise while keeping the line structure section detection needs."""
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\xa0", " ")
    # CUAD plain text carries literal, sometimes misspelled entity remnants
    text = re.sub(r"&[a-z]?[bn]bsp;", " ", text)
    text = text.replace("&amp;", "&")
    text = re.sub(r"[ \t]+", " ", text)
    lines = [line.strip() for line in text.split("\n")]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def parse_document(doc: dict, raw_root: str | Path) -> dict:
    raw_path = destination(doc, raw_root)
    raw_bytes = raw_path.read_bytes()
    raw = raw_bytes.decode("utf-8", errors="replace")
    if raw_path.suffix == ".htm" or raw_path.suffix == ".html":
        text = parse_html(raw)
    else:
        text = parse_txt(raw)
    if not text:
        raise ValueError(f"{raw_path} parsed to empty text")
    return {
        "doc_id": doc.get("doc_id") or derive_doc_id(doc),
        "source_path": str(raw_path),
        "raw_sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "text": text,
    }


def parse_all(
    manifest_path: str | Path = "corpus/manifest.json",
    raw_root: str | Path = "corpus/raw",
    out_root: str | Path = "corpus/normalized",
) -> list[Path]:
    manifest = load_manifest(manifest_path)
    out_root = Path(out_root)
    out_root.mkdir(parents=True, exist_ok=True)
    written = []
    for doc in manifest["documents"]:
        normalized = parse_document(doc, raw_root)
        out_path = out_root / f"{normalized['doc_id']}.json"
        out_path.write_text(json.dumps(normalized) + "\n")
        written.append(out_path)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default="corpus/manifest.json")
    parser.add_argument("--raw", default="corpus/raw")
    parser.add_argument("--out", default="corpus/normalized")
    args = parser.parse_args(argv)
    written = parse_all(args.manifest, args.raw, args.out)
    total_chars = sum(len(json.loads(p.read_text())["text"]) for p in written)
    print(f"normalized {len(written)} documents, {total_chars} characters")
    return 0


if __name__ == "__main__":
    sys.exit(main())
