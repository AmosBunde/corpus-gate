# M3 finding: the agent is a bounded loop over honest tools

Milestone M3 delivered the tool layer (#53, PR #57), the agent loop with the six-step budget and forced answer (#54, PR #58), and trace capture with the replay CLI (#55, PR #59); the agent variant is registered in the eval harness alongside the others. The scored delta against the RAG champion (#56) remains blocked on the pinned judge, which needs `ANTHROPIC_API_KEY`; this finding records what shipped and what the mechanical evidence shows.

## What exists now

- Three tools behind one chokepoint: `search_corpus`, `read_document`, and `cross_reference`, all funneling every retrieved chunk through `observed_chunk_ids`. The agent can only cite what a tool actually returned; a citation to an unobserved chunk is dropped and counted, structurally, before any judge sees the answer.
- A six-step loop with the budget stated in the prompt as a countdown. At the final step the model is forced to answer with what it has; the forced flag is recorded in the trace. Unknown actions and bad tool arguments become observations the loop continues through, not exceptions.
- Per-episode traces (every step, action, observation summary, and the final answer with its dropped-citation count) persisted with the run, and a replay CLI that renders any episode step by step for debugging.
- A flat, all-nullable step schema. Structured outputs demand every field present on every step; optionality lives in the values, not the shape.

## Decisions that will matter later

1. **Citation honesty is enforced at the tool boundary, not requested in the prompt.** The prompt asks for citations from observations; the code makes anything else impossible to emit. When the fine-tuned variant arrives, it inherits this floor for free.
2. **The budget countdown lives in the prompt text.** The model is told "you have N of 6 steps remaining" each turn, and the forced final answer means an indecisive model degrades to a refusal rather than an error. Episode length is a measured property of the trace, not a hope.
3. **Traces are first-class run artifacts.** The runner persists them whenever a variant exposes them, so the same eval command that scores the agent also captures why each answer looks the way it does. Debugging a bad answer is a replay, not a rerun.

## What validation caught

The scripted-backend tests proved the loop's contract cheaply: budget exhaustion forces an answer, fabricated citations are dropped with the counter incremented, unknown documents become observations, and the countdown text actually counts down. None of this needed a model. What did need a model, live serving against llama.cpp, later exposed two defects the fakes could not: a transient unusable completion killed a whole eval run (#76), and the JSON-object grammar without a schema let the model drift citations into pair arrays that the normalizer silently discarded (#79). Both fixes landed with transport-level tests. The standing lesson holds a third time: fakes prove contracts, only live runs prove behavior.

## Pending owner input

The M3 exit criterion in the work breakdown is a scored delta table, agent versus the RAG champion, judged by the pinned judge. That requires `ANTHROPIC_API_KEY`. The harness is ready: `make eval VARIANT=agent` collects, the judge scores as a separate pass, and the gate compares. The delta table belongs on #56 the day the key exists.
