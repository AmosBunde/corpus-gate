# M4 finding: the adapter earns nothing until the gate says so

Milestone M4 delivered pair curation with the decontamination gate (#60, PR #65), the LoRA training loop with a CPU dry-run mode (#61, PR #66), the adapter registry with pointer-move rollback (#62, PR #67), and the promote-or-reject gate against the champion (#63, PR #68). The four-variant scored run (#64) awaits both the pinned judge key and a GPU session; this finding records the machinery and the measured decontamination evidence.

## What exists now

- 140 training pairs curated deterministically from the real corpus: 60 format pairs (real chunk presented, schema answer citing its real chunk ID demanded), 60 terminology pairs (defined terms extracted from the contracts' own quoted definitions), 20 refusal pairs (questions the corpus cannot support, answered with the refusal shape). No model in the curation loop; the set reproduces from the corpus alone and is hash-manifested.
- A decontamination gate at cosine similarity 0.85 against every eval question and reference answer, embedded with the pinned local model so the check never leaves the boundary. Result on the committed report: 140 candidates, 140 kept, 0 dropped, with the closest kept pair at 0.842 similarity. The margin is thin and measured, which is the point: the report proves the check bites exactly at the line, rather than passing because nothing came near it.
- One training code path for GPU and CPU. `resolve_device` refuses CPU unless `FINETUNE_ALLOW_CPU=1`, and the dry-run profile swaps in a tiny base model to prove the loop end to end on this machine: 2 steps, loss recorded, adapter and metadata written. The committed dry-run artifact carries `"dry_run": true` and the registry refuses to promote any adapter so marked.
- A registry whose champion is a pointer. Promotion copies the adapter in and moves the pointer; rollback moves the pointer back. Nothing about serving changes except which adapter the pointer names.

## Decisions that will matter later

1. **The adapter teaches behavior, not facts.** Format following, corpus terminology, refusal shape. Facts stay in the corpus where retrieval finds them; an adapter that memorized facts would rot the moment the corpus changed and would leak eval answers besides.
2. **Decontamination is embedding similarity, not string matching.** A paraphrased eval question would sail through exact-match filtering; at 0.85 cosine with the closest kept pair measured at 0.842, the committed report shows the gate operating in the region where it matters.
3. **Dry-run adapters are structurally barred from the champion.** The metadata flag is checked at promotion time, so the CPU proof of the loop can never be mistaken for a trained artifact.

## Pending owner input

Real training needs a rented 24 GB GPU session for the pinned Qwen2.5-7B-Instruct base; the scored four-variant gate run (#64) additionally needs `ANTHROPIC_API_KEY` for the pinned judge. Both are single owner actions. Until then the fine-tune row of the scoreboard does not exist, and nothing in the repository pretends it does.
