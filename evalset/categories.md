# Eval categories

Every question in `questions.jsonl` belongs to exactly one of four categories. Categories exist because the gate compares variants per category: an agent loop that helps cross-reference questions while hurting refusal behavior must be visible as exactly that.

## lookup

A single fact or short passage from one document: a figure, a date, a name, the substance of one disclosure. The gold evidence is one anchor (occasionally two when the same fact appears in both the narrative and the statements). Grading intent: the exact fact, correctly qualified (fiscal period, units, direction of change), with a citation into the right document section. A correct number with a wrong or missing citation is a failing answer.

## cross_reference

Requires evidence from two or more documents, or two clearly separate sections, combined correctly: comparing a figure across issuers, tracking a change between a 10-K and a later 10-Q, connecting an 8-K event to its 10-K context. Gold evidence is two or more anchors, and the rubric requires each leg of the comparison to be grounded. Grading intent: both legs correct and cited; one correct leg with a fabricated other leg scores as a failure, not as half credit.

## synthesis

Aggregation or characterization over multiple passages: summarizing risk themes, describing a segment structure end to end, explaining a year-over-year narrative. There may be several defensible phrasings; the rubric pins the claims that must be present and cited rather than exact wording. Grading intent: coverage of the rubric claims, no invented claims, citations for each claim that needs one.

## refusal

Questions the system must decline: issuers not in the corpus, periods outside its coverage, future events, and information classes that SEC filings do not disclose (unit sales Apple does not report, plant-level production, analyst opinions). Gold evidence is empty by definition. Grading intent: a clear refusal stating that the corpus does not contain the answer, the correct reason, no fabricated figures, and no citations. A fluent answer with a made-up number is the worst possible outcome and scores zero.

## Evidence anchors

Non-refusal questions pin gold evidence as `DOCID#section-slug`:

- `DOCID` is `TICKER-FORM-FILINGDATE` derived from `corpus/manifest.json`, for example `AAPL-10-K-2025-10-31`.
- The section slug names a stable structural unit of the filing, lowercase, with `.` and `-` as separators.

Slug conventions by form type:

| Form | Slugs | Examples |
| --- | --- | --- |
| 10-K | `item-<n><letter>` following the Form 10-K item numbering | `item-1`, `item-1a`, `item-7`, `item-8` |
| 10-Q | `part<n>-item<n>` | `part1-item1`, `part1-item2`, `part2-item1a` |
| 8-K | `item-<n>.<nn>` following the Form 8-K item numbering | `item-2.02`, `item-8.01`, `item-9.01` |
| DEF 14A | named sections, kebab case | `director-nominees`, `executive-compensation`, `summary-compensation-table` |

The M2 chunker is required to mint chunk IDs that carry these anchors (every chunk records its document and section slug), which is how anchors written before any ingestion code exist stay resolvable to chunk sets afterward. Retrieval metrics count a hit when a retrieved chunk's document and section match a gold anchor.

## Balance

The complete set (after the second authoring PR) holds 50 or more questions with at least 10 per category, and exactly 10 questions marked `"smoke": true` spanning all four categories form the CI smoke slice. The current state is validated by `make eval-set`; completeness is enforced with the `--complete` flag once the second half lands.
