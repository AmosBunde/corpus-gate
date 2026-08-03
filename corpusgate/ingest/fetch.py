"""Reproducible corpus acquisition: CUAD contracts and SEC EDGAR documents.

Every document is pinned in corpus/manifest.json: EDGAR documents by
accession number, CUAD contracts by the sha256 of the CUAD data
archive plus the exact contract title, so two machines fetching the
manifest get byte-identical inputs. The SEC fair-access policy
requires a descriptive User-Agent with contact information and caps
request rates; this module sends one request at a time with a fixed
pause, far under the published ceiling. Set SEC_USER_AGENT to your
own contact string when fetching.
"""

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

ARCHIVE_BASE = "https://www.sec.gov/Archives/edgar/data"
DEFAULT_USER_AGENT = "CorpusGate (github.com/AmosBunde/corpus-gate)"
REQUEST_INTERVAL_S = 0.5


def document_url(doc: dict) -> str:
    """Archive URL for a manifest entry: CIK, dashless accession, primary document."""
    accession = doc["accession"].replace("-", "")
    return f"{ARCHIVE_BASE}/{doc['cik']}/{accession}/{doc['primary_document']}"


def destination(doc: dict, dest_root: str | Path) -> Path:
    """Stable on-disk location per source type."""
    if doc.get("source") == "cuad":
        return Path(dest_root) / "CUAD" / f"{doc['doc_id']}.txt"
    form = doc["form"].replace(" ", "").replace("/", "-")
    return (
        Path(dest_root) / doc["ticker"] / f"{form}_{doc['filing_date']}_{doc['primary_document']}"
    )


def cuad_archive_path(dest_root: str | Path) -> Path:
    return Path(dest_root).parent / "cache" / "cuad-data.zip"


def ensure_cuad_archive(cuad_cfg: dict, dest_root: str | Path, user_agent: str) -> Path:
    """Download the CUAD data archive once and verify it against the pinned sha256."""
    archive = cuad_archive_path(dest_root)
    if not archive.exists():
        archive.parent.mkdir(parents=True, exist_ok=True)
        request = urllib.request.Request(cuad_cfg["url"], headers={"User-Agent": user_agent})
        with urllib.request.urlopen(request, timeout=300) as response:
            archive.write_bytes(response.read())
        print(f"fetched CUAD archive -> {archive}")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    if digest != cuad_cfg["sha256"]:
        raise ValueError(f"CUAD archive sha256 mismatch: {digest} != {cuad_cfg['sha256']}")
    return archive


def cuad_texts(archive: str | Path, member: str) -> dict[str, str]:
    """Full contract text per CUAD title, read from the pinned archive member."""
    with zipfile.ZipFile(archive) as z, z.open(member) as f:
        data = json.load(f)
    return {c["title"]: c["paragraphs"][0]["context"] for c in data["data"]}


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

    cuad_docs = [d for d in manifest["documents"] if d.get("source") == "cuad"]
    cuad_missing = [d for d in cuad_docs if not destination(d, dest_root).exists()]
    if cuad_missing:
        archive = ensure_cuad_archive(manifest["cuad"], dest_root, user_agent)
        texts = cuad_texts(archive, manifest["cuad"]["member"])
        for doc in cuad_missing:
            dest = destination(doc, dest_root)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(texts[doc["title"]])
            print(f"extracted {doc['doc_id']} -> {dest}")
            downloaded += 1
    skipped += len(cuad_docs) - len(cuad_missing)

    for doc in manifest["documents"]:
        if doc.get("source") == "cuad":
            continue
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
