# M0 finding: scaffold

Milestone M0 delivered the package skeleton (#6, PR #10), the Makefile (#7, PR #11), the four-service compose scaffold (#8, PR #12), and CI (#9, PR #13). All four merged with the validation records in their PR bodies; the last two merged with CI green, and the post-merge run on main is green.

## What exists now

- `corpusgate` installs, lints clean under ruff, and passes its tests on Python 3.12. Every subpackage docstring names the milestone that fills it, and a test fails if a future subpackage arrives undocumented.
- Every make target from README section 8 exists. Real targets run real tools; staged targets exit 2 naming their milestone, so the end-to-end chain fails at the first unimplemented stage by design.
- `docker compose up --build` brings up api, ui, vectordb, and llm; each service answered its probe during validation. The llm service is a health-only stub whose M2 replacement recipe sits beside it in the compose file.
- CI enforces ruff, pytest, and compose config validation on every PR. The M1 smoke job attachment point is documented in the workflow.

## What M0 validation taught

1. **Default ports collide on real machines.** The first `docker compose up` failed because an unrelated project already bound 8000 and 3000 on the development machine. The fix keeps contract defaults and adds environment overrides (`API_PORT`, `UI_PORT`, `QDRANT_PORT`, `LLM_PORT`, and `PORT` for `make serve`). The failure mode without an override is a loud bind error, which is acceptable; silent misrouting would not be.
2. **A probe can hit the wrong service and look healthy.** An early `make serve` check returned `{"status": "ok"}` from the other project squatting on port 8000. The giveaway was the missing `version` field. Lesson adopted: every CorpusGate health payload carries `version` and `model_backend`, and any probe that does not assert those fields is not a verification. This habit matters more in M2 and beyond, when eval runs will probe variants and must never score the wrong one.
3. **Self-validating changes are the cheapest reviews.** The CI PR ran its own workflow before merge; the compose PR was validated by bringing the stack up and probing every service. Where a change can prove itself, the PR body should show the proof rather than describe intent.

## Open decisions for the owner

- **License.** The repository has none, and `pyproject.toml` deliberately omits the field. Publishing a public portfolio repository without a license leaves the default all-rights-reserved state; this is a one-line decision once made.

## Rejected alternatives

- A real llama.cpp container at M0 was rejected: it cannot start without a model file, and shipping or downloading a multi-gigabyte model to prove a scaffold would couple M0 to M2 concerns for no eval benefit.
- A single CI job running lint plus tests was rejected in favor of separate jobs, trading one duplicated dependency install (seconds today) for failure messages that name their gate in the check list.

No variants existed to gate in this milestone, so there are no scoreboard entries or judge-agreement numbers to report; those begin with M1.
