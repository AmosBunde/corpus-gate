# M1 finding: the eval set comes first

Milestone M1 delivered the corpus selection (#24, PR #30), the eval set in two parts (#25 PR #31, #26 PR #32), the runner and variant interface (#27, PR #33), the pinned judge with the human-audit protocol (#28, PR #34), and retrieval metrics, the scoreboard, and the live CI smoke slice (#29, PR #35). Hard rule 1 now holds mechanically: `evalset/questions.jsonl` carries 50 graded questions across four categories, and `make eval` scores an arbitrary variant, before any ingestion, chunking, or retrieval code exists.

## What exists now

- A pinned corpus: 21 EDGAR filings from three issuers, fetched reproducibly by accession number, with a committed demo slice.
- 50 questions (15 lookup, 12 cross_reference, 11 synthesis, 12 refusal) with rubrics, reference answers, and gold evidence anchors; 10 marked as the smoke slice spanning all categories. `make eval-set` enforces schema and completeness.
- A variant interface and runner that record answers, citations, ranked retrieval, latency, and token usage into run directories; scoring is a separate pass so a re-judge never re-runs a variant.
- A pinned judge (claude-sonnet-5, prompt version 1) scoring per rubric criterion through structured outputs, with a deterministic mock backend for CI; every run gets a blind 15-question human-audit sheet and an agreement computation.
- Mechanical retrieval metrics (hit rate at 5, MRR) over gold anchors, a scoreboard rendering the README section 11 shape, and a CI smoke job that runs the entire harness on every pull request.

## Decisions that will matter later

1. **Evidence anchors before chunks exist.** Gold evidence is pinned as `DOCID#section-slug` against the manifest, and the match rule (anchor equals the chunk ID prefix before the ordinal separator) is settled and tested now. The M2 chunker inherits a contract; anchors written in M1 stay resolvable forever.
2. **Refusal questions were absence-checked, not assumed.** Every claimed absence was grepped against extracted corpus text before the question was written. The near-miss that shaped the process: an Apple fiscal 2020 question is only safe because the FY2020 figures were verified absent, since a 10-K carries three years of comparatives and a five-year stock chart.
3. **The judge has no temperature knob, by API design.** The pinned model rejects sampling parameters, so determinism rests on pinned prompt bytes, disabled thinking, and a structured-output schema. This is better for auditability: nothing about the judge can be quietly tuned.
4. **The bracket variants are harness insurance.** The oracle (reference answers, gold anchors cited) must score 100 with perfect retrieval; the echo (refuses everything) must score only where refusing is correct. CI enforces both on every PR, so harness rot breaks a build instead of quietly bending scores.

## What validation caught

Resolving the latest run by directory name sorted `echo-` before `oracle-` alphabetically, so the echo chain silently re-judged the oracle run and reported a healthy-looking number for the wrong target. This is the same failure shape as the M0 wrong-service probe, in a second costume. The fix resolves by modification time, and every score line prints the run path it scored. Standing lesson, now twice earned: a validation that does not name its target is not a validation.

## Judge-human agreement: protocol ready, numbers pending

The audit protocol is implemented end to end: deterministic blind subsample, scoring sheet, mean absolute difference and pass/fail agreement against the pinned threshold. What does not exist yet is a live judge run to audit, because this environment has no `ANTHROPIC_API_KEY`. Unblocking is a single owner action: provide the key (as a local environment variable for a one-off run, and optionally as a repository secret if CI should ever run the live judge), then `make eval VARIANT=oracle` followed by human scoring of the sheet. The first agreement numbers belong in the M2 finding alongside the baseline, where they will contextualize the first real scores.

## Rejected alternatives

- Paragraph-level anchors were rejected: no parser can promise stable paragraph boundaries on this HTML, and an anchor the chunker cannot honor is worse than a coarser one it can. Section-level anchors are the finest unit all 21 documents support.
- Judging inline during the answer run was rejected: separating collection from scoring makes re-judging free, which matters as soon as a judge prompt revision or a re-audit is needed against API-priced variants.
- A temperature-zero judge was the original design and was rejected by reality: the pinned model does not accept the parameter. The replacement (pins plus structured outputs) is stronger.
- Running the live judge in the CI smoke slice was rejected for now: CI has no key, and a smoke job that proves the machinery mechanically on every PR is worth more than one that silently skips when a secret is absent.

## Addendum: the corpus pivot (2026-08-04)

After M1 first closed, the owner pinned the corpus to public commercial contracts: CUAD (CC BY 4.0) supplemented with SEC EDGAR exhibit 10 material contracts. The original selection of general EDGAR filings was therefore an unapproved substitution and was retired. The realignment ran as three green-CI units (#38 acquisition, #39 lookup and refusal re-authoring, #40 cross-reference and synthesis re-authoring plus legacy retirement), with the harness untouched throughout: schema, runner, judge, metrics, scoreboard, and smoke needed no changes, which is the eval-first architecture paying rent.

What the contracts corpus improved: redacted confidential terms and incompletely dated filings give refusal and lookup questions discriminators the filings corpus never had, since a candidate that invents a redacted figure now fails on a question designed to catch exactly that. One style exception is on record: the sponsorship agreement names the campaign National Get Fit Don't Sit Day, and the quoted proper name keeps its contraction because accuracy to source text outranks house style for quoted material.

Two process lessons joined the ledger. A pipeline's exit code is the last command's, so piping pytest through head masked six failing tests and a PR opened red until CI caught it; validation commands now run bare. And git add -A swept an 18 MB downloaded archive into a commit moments after a fetch step wrote it; explicit paths are the rule after any step that writes large artifacts.
