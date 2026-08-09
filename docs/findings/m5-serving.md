# M5 finding: the boundary holds, and the numbers are measured

Milestone M5 delivered the authenticated serving API over the real local runtime (#69, PR #74), per-request accounting with the metrics endpoint (#70, PR #75), the UI query box with streamed answers (#71, PR #78), inline cited passages with distinct refusals (#72, PR #81), and this experiment (#73): a load probe, the cost table, and the closing findings. Two defects found only by live use were fixed along the way: a transient unusable completion no longer kills a run (#76, PR #77), and the answer schema is now enforced as a llama.cpp grammar so citations cannot drift out of shape (#79, PR #80).

Serving conditions for every number below: Qwen2.5-7B-Instruct, Q4_K_M GGUF, llama.cpp server, CPU only, context 4096, on a 32 GB machine, with `MODEL_BACKEND=local`. No corpus content leaves the machine; the API backend remains a development convenience that this milestone never needed.

## The full-set local run

The 51-question eval set ran end to end against the local model (run `rag-20260809T125036Z`), the first complete measurement of the deployment target on the whole set.

- All 51 questions produced recorded answers. One question absorbed two 300-second timeouts during a memory-pressure period and degraded to a refusal-shaped payload exactly as the #76 fix intends; the run continued.
- Retrieval, mechanical and judge-free, over the 39 non-refusal questions: hit rate at 5 of 0.564, MRR of 0.455.
- Latency across the run: p50 of 139 seconds, p95 of 509 seconds. The tail reflects hours of host swap pressure, which is a real deployment hazard on a shared 32 GB box, not an artifact worth hiding.
- Tokens: mean 1,042 prompt and 157 completion per query; 53,150 prompt and 7,986 completion in total.
- Behavior by category: lookup answered with citations 13 of 16; the refusal category refused 11 of 12; cross_reference over-refused, 9 of 12, because one shot of five retrieved chunks rarely covers two documents. That over-refusal is the mechanical case for the M3 agent, whose `cross_reference` tool retrieves per document; the judged comparison awaits the pinned judge.

## Load probe

Eight queries from the smoke slice against `/query`, after the eval run released the server, same conditions as above.

| Concurrency | Succeeded | p50 | p95 |
|---|---|---|---|
| 1 | 8 of 8 | 60.5 s | 448.8 s |
| 2 | 8 of 8 | 152.1 s | 492.8 s |

Client wall latency and the server's own `/metrics` aggregates agreed within about two seconds at concurrency 1 and within a tenth of a second at concurrency 2, which validates the accounting path. The p95 outliers are the same swap-pressure tail the eval run saw. Concurrency 2 multiplied the p50 by roughly 2.5 rather than the ideal 2: llama.cpp interleaves the two streams across the same cores and the prompt cache thrashes between them, so on this hardware concurrency buys queue fairness at a real cost, not throughput.

## Cost per query

Measured token counts from the full run, priced two ways. Local serving has zero marginal token cost; its price is latency. The api column applies the published claude-sonnet-5 rates pinned on 2026-08-09 ($3.00 per million input tokens, $15.00 per million output tokens) to the same measured token counts.

| | Mean tokens per query | Marginal cost per query | p50 latency |
|---|---|---|---|
| Local (measured) | 1,042 in, 157 out | $0 | 60.5 s interactive, 139 s under eval load |
| API equivalent (priced) | 1,042 in, 157 out | $0.0055 | not measured here |

At these rates the entire 51-question eval run would cost about $0.28 through the api. The trade is stark and now quantified: the local path pays roughly a minute per answer to keep the corpus inside the boundary; the api path pays about half a cent per query and the corpus leaves the machine.

## What remains owner-gated

The scored scoreboard rows (four category scores and overall per variant, champion marked) require the pinned judge, which requires `ANTHROPIC_API_KEY`; the fine-tune row additionally requires a GPU training session. The mock judge scored this run to prove the chain runs end to end, and those numbers are deliberately not reported as results anywhere, because a deterministic heuristic is not the pinned judge. README section 11 carries the mechanical row this milestone earned and states plainly what the judged columns await.
