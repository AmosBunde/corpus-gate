"""Question schema and validation for the eval set.

The eval set is version zero of the product, so its schema is enforced
mechanically from the first question. Every non-refusal question pins
gold evidence anchors of the form DOCID#section-slug, where DOCID is
TICKER-FORM-FILINGDATE derived from corpus/manifest.json and the
section slug names a stable structural unit of the filing (item-1a,
part1-item1, item-2.02). The M2 chunker is required to mint chunk IDs
that carry these anchors, which is what makes anchors written today
resolvable to chunk sets forever.
"""

import argparse
import json
import re
import sys
from pathlib import Path

CATEGORIES = ("lookup", "cross_reference", "synthesis", "refusal")
REQUIRED_FIELDS = (
    "id",
    "category",
    "question",
    "reference_answer",
    "rubric",
    "gold_anchors",
    "smoke",
)
ID_RE = re.compile(r"^q-\d{3}$")
SECTION_RE = re.compile(r"^[a-z0-9]+([.-][a-z0-9]+)*$")


def doc_id(doc: dict) -> str:
    """Stable document identifier: TICKER-FORM-FILINGDATE, form made path safe."""
    form = doc["form"].replace(" ", "").replace("/", "-")
    return f"{doc['ticker']}-{form}-{doc['filing_date']}"


def manifest_doc_ids(manifest_path: str | Path) -> set[str]:
    manifest = json.loads(Path(manifest_path).read_text())
    return {doc.get("doc_id") or doc_id(doc) for doc in manifest["documents"]}


def parse_anchor(anchor: str) -> tuple[str, str]:
    """Split DOCID#section-slug; raises ValueError on malformed anchors."""
    if anchor.count("#") != 1:
        raise ValueError(f"anchor {anchor!r} must contain exactly one #")
    doc, section = anchor.split("#")
    if not doc or not SECTION_RE.match(section):
        raise ValueError(f"anchor {anchor!r} has a malformed document id or section slug")
    return doc, section


def validate_question(q: dict, known_docs: set[str]) -> list[str]:
    """All schema violations for one question, empty when valid."""
    errors = []
    for field in REQUIRED_FIELDS:
        if field not in q:
            return [f"{q.get('id', '<no id>')}: missing field {field}"]
    qid = q["id"]
    if not ID_RE.match(qid):
        errors.append(f"{qid}: id must match q-NNN")
    if q["category"] not in CATEGORIES:
        errors.append(f"{qid}: unknown category {q['category']!r}")
    if not q["question"].strip() or not q["reference_answer"].strip():
        errors.append(f"{qid}: question and reference_answer must be non-empty")
    if (
        not isinstance(q["rubric"], list)
        or not q["rubric"]
        or not all(isinstance(r, str) and r.strip() for r in q["rubric"])
    ):
        errors.append(f"{qid}: rubric must be a non-empty list of non-empty strings")
    if not isinstance(q["smoke"], bool):
        errors.append(f"{qid}: smoke must be a boolean")
    anchors = q["gold_anchors"]
    if not isinstance(anchors, list):
        errors.append(f"{qid}: gold_anchors must be a list")
        return errors
    if q["category"] == "refusal":
        if anchors:
            errors.append(f"{qid}: refusal questions must have no gold anchors")
    elif not anchors:
        errors.append(f"{qid}: non-refusal questions need at least one gold anchor")
    for anchor in anchors:
        try:
            doc, _section = parse_anchor(anchor)
        except ValueError as exc:
            errors.append(f"{qid}: {exc}")
            continue
        if doc not in known_docs:
            errors.append(f"{qid}: anchor document {doc!r} is not in corpus/manifest.json")
    return errors


def load_questions(path: str | Path) -> list[dict]:
    questions = []
    for line_no, line in enumerate(Path(path).read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            questions.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_no}: not valid JSON ({exc})") from exc
    return questions


def validate(
    questions_path: str | Path,
    manifest_path: str | Path,
    require_complete: bool = False,
) -> list[str]:
    """All violations across the eval set; empty means the set is valid."""
    known_docs = manifest_doc_ids(manifest_path)
    questions = load_questions(questions_path)
    errors = []
    seen_ids: set[str] = set()
    counts = dict.fromkeys(CATEGORIES, 0)
    smoke_by_category = dict.fromkeys(CATEGORIES, 0)
    for q in questions:
        errors.extend(validate_question(q, known_docs))
        qid = q.get("id")
        if qid in seen_ids:
            errors.append(f"{qid}: duplicate id")
        seen_ids.add(qid)
        if q.get("category") in counts:
            counts[q["category"]] += 1
            if q.get("smoke") is True:
                smoke_by_category[q["category"]] += 1
    if require_complete:
        if len(questions) < 50:
            errors.append(f"complete set needs 50+ questions, found {len(questions)}")
        for category, count in counts.items():
            if count < 10:
                errors.append(f"complete set needs 10+ {category} questions, found {count}")
        total_smoke = sum(smoke_by_category.values())
        if total_smoke != 10:
            errors.append(f"complete set needs exactly 10 smoke questions, found {total_smoke}")
        if any(count == 0 for count in smoke_by_category.values()):
            errors.append("smoke slice must span all four categories")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", default="evalset/questions.jsonl")
    parser.add_argument("--manifest", default="corpus/manifest.json")
    parser.add_argument("--complete", action="store_true", help="enforce full-set counts")
    args = parser.parse_args(argv)
    errors = validate(args.questions, args.manifest, require_complete=args.complete)
    questions = load_questions(args.questions)
    counts: dict[str, int] = {}
    for q in questions:
        counts[q.get("category", "?")] = counts.get(q.get("category", "?"), 0) + 1
    summary = ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
    print(f"{len(questions)} questions: {summary}")
    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        return 1
    print("eval set valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
