"""Reproducible corpus acquisition from SEC EDGAR.

Every document is pinned by accession number in corpus/manifest.json,
so two machines fetching the manifest get byte-identical filings. The
SEC fair-access policy requires a descriptive User-Agent with contact
information and caps request rates; this module sends one request at
a time with a fixed pause, far under the published ceiling. Set
SEC_USER_AGENT to your own contact string when fetching.
"""

import argparse
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

ARCHIVE_BASE = "https://www.sec.gov/Archives/edgar/data"
DEFAULT_USER_AGENT = "CorpusGate (github.com/AmosBunde/corpus-gate)"
REQUEST_INTERVAL_S = 0.5


def document_url(doc: dict) -> str:
    """Archive URL for a manifest entry: CIK, dashless accession, primary document."""
    accession = doc["accession"].replace("-", "")
    return f"{ARCHIVE_BASE}/{doc['cik']}/{accession}/{doc['primary_document']}"


def destination(doc: dict, dest_root: str | Path) -> Path:
    """Stable on-disk location: <root>/<ticker>/<FORM>_<date>_<primary_document>."""
    form = doc["form"].replace(" ", "").replace("/", "-")
    return (
        Path(dest_root) / doc["ticker"] / f"{form}_{doc['filing_date']}_{doc['primary_document']}"
    )


def load_manifest(manifest_path: str | Path) -> dict:
    manifest = json.loads(Path(manifest_path).read_text())
    if not manifest.get("documents"):
        raise ValueError(f"{manifest_path} lists no documents")
    return manifest


def fetch(manifest_path: str | Path, dest_root: str | Path) -> tuple[int, int]:
    """Download every manifest document that is not already present.

    Returns (downloaded, skipped). Existing non-empty files are never
    re-downloaded, so the command is idempotent and resumable.
    """
    manifest = load_manifest(manifest_path)
    user_agent = os.environ.get("SEC_USER_AGENT", DEFAULT_USER_AGENT)
    downloaded = 0
    skipped = 0
    for doc in manifest["documents"]:
        dest = destination(doc, dest_root)
        if dest.exists() and dest.stat().st_size > 0:
            skipped += 1
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        request = urllib.request.Request(document_url(doc), headers={"User-Agent": user_agent})
        with urllib.request.urlopen(request, timeout=60) as response:
            dest.write_bytes(response.read())
        print(f"fetched {doc['ticker']} {doc['form']} {doc['filing_date']} -> {dest}")
        downloaded += 1
        time.sleep(REQUEST_INTERVAL_S)
    return downloaded, skipped


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default="corpus/manifest.json")
    parser.add_argument("--dest", default="corpus/raw")
    args = parser.parse_args(argv)
    downloaded, skipped = fetch(args.manifest, args.dest)
    print(f"done: {downloaded} downloaded, {skipped} already present")
    return 0


if __name__ == "__main__":
    sys.exit(main())
