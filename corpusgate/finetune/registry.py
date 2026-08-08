"""The adapter registry: versioned artifacts, one champion pointer, plain files.

Every version records its base model, training run metadata, the
sha256 of the exact pair manifest it trained on, and its
decontamination report, so the provenance chain from corpus to
adapter is verifiable end to end. The champion is a pointer in
index.json; promotion and rollback are the same one-line move, which
is what makes rollback boring, and boring is the goal. Nothing is
ever deleted.
"""

import argparse
import hashlib
import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

DEFAULT_ROOT = "registry"


def _index_path(root: str | Path) -> Path:
    return Path(root) / "index.json"


def load_index(root: str | Path = DEFAULT_ROOT) -> dict:
    path = _index_path(root)
    if path.exists():
        return json.loads(path.read_text())
    return {"champion_adapter": None, "versions": {}}


def _save_index(index: dict, root: str | Path) -> None:
    _index_path(root).write_text(json.dumps(index, indent=2) + "\n")


def register(
    version: str,
    candidate_dir: str | Path,
    root: str | Path = DEFAULT_ROOT,
) -> dict:
    """Move a candidate (pairs, report, adapter) into a numbered version."""
    root = Path(root)
    candidate_dir = Path(candidate_dir)
    index = load_index(root)
    if version in index["versions"]:
        raise ValueError(f"version {version!r} already registered")
    pairs_path = candidate_dir / "pairs.jsonl"
    report_path = candidate_dir / "decontam_report.md"
    training_meta_path = candidate_dir / "adapter" / "training_run.json"
    for required in (pairs_path, report_path, training_meta_path):
        if not required.exists():
            raise FileNotFoundError(f"candidate is incomplete: {required} missing")
    version_dir = root / version
    if version_dir.exists():
        raise ValueError(f"{version_dir} already exists")
    shutil.move(str(candidate_dir), str(version_dir))
    training_meta = json.loads((version_dir / "adapter" / "training_run.json").read_text())
    entry = {
        "created_at": datetime.now(UTC).isoformat(),
        "base_model": training_meta["base_model"],
        "dry_run": training_meta["dry_run"],
        "steps": training_meta["steps"],
        "adapter_dir": str(version_dir / "adapter"),
        "pairs_manifest_sha256": hashlib.sha256(
            (version_dir / "pairs.jsonl").read_bytes()
        ).hexdigest(),
        "decontam_report": str(version_dir / "decontam_report.md"),
    }
    index["versions"][version] = entry
    _save_index(index, root)
    return entry


def promote(version: str, root: str | Path = DEFAULT_ROOT) -> dict:
    """Point the champion at a registered version; rollback is the same move."""
    index = load_index(root)
    if version not in index["versions"]:
        raise ValueError(f"unknown version {version!r}")
    if index["versions"][version]["dry_run"]:
        raise ValueError(f"{version} is a dry-run adapter and cannot be champion")
    index["champion_adapter"] = version
    _save_index(index, root)
    return index


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p_reg = sub.add_parser("register")
    p_reg.add_argument("version")
    p_reg.add_argument("--candidate", default="registry/candidate")
    p_pro = sub.add_parser("promote", help="set or roll back the champion pointer")
    p_pro.add_argument("version")
    sub.add_parser("list")
    args = parser.parse_args(argv)
    if args.command == "register":
        entry = register(args.version, args.candidate)
        print(f"registered {args.version}: {entry['base_model']} "
              f"(dry_run={entry['dry_run']}, pairs {entry['pairs_manifest_sha256'][:12]})")
    elif args.command == "promote":
        index = promote(args.version)
        print(f"champion_adapter is now {index['champion_adapter']}")
    else:
        index = load_index()
        champion = index["champion_adapter"]
        for version, entry in sorted(index["versions"].items()):
            marker = " <- champion" if version == champion else ""
            print(f"{version}: {entry['base_model']} dry_run={entry['dry_run']} "
                  f"steps={entry['steps']}{marker}")
        if not index["versions"]:
            print("no versions registered")
    return 0


if __name__ == "__main__":
    sys.exit(main())
