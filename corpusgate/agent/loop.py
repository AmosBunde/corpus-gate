"""The agent loop: six model steps, tools in between, a guaranteed schema answer.

Each step the model either calls a tool or answers; observations
append to the working transcript, and the citable set grows only
from what tools actually returned. Step six forces the answer, so no
request can hang or wander. Traces record every step for replay.
"""

import time

from corpusgate.agent.tools import TOOL_DESCRIPTIONS, Toolbox, observed_chunk_ids
from corpusgate.evals.rag import ANSWER_SCHEMA, _normalize, get_backend
from corpusgate.evals.variants import Citation, VariantAnswer

MAX_STEPS = 6

STEP_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "enum": ["search_corpus", "read_document", "cross_reference", "answer"],
        },
        "query": {"type": ["string", "null"]},
        "doc_id": {"type": ["string", "null"]},
        "section": {"type": ["string", "null"]},
        "doc_ids": {"type": ["array", "null"], "items": {"type": "string"}},
        "answer": {"type": ["string", "null"]},
        "citations": {
            "type": ["array", "null"],
            "items": {
                "type": "object",
                "properties": {"chunk_id": {"type": "string"}, "quote": {"type": "string"}},
                "required": ["chunk_id", "quote"],
                "additionalProperties": False,
            },
        },
        "refused": {"type": ["boolean", "null"]},
    },
    "required": [
        "action",
        "query",
        "doc_id",
        "section",
        "doc_ids",
        "answer",
        "citations",
        "refused",
    ],
    "additionalProperties": False,
}

STEP_PROMPT = """You answer questions about a corpus of commercial contracts by using tools.

Tools:
- {tool_search}
- {tool_read}
- {tool_xref}

Rules: every factual claim in a final answer must be cited by chunk_id from
tool results with a short quote. If the corpus does not support an answer,
answer with refused true and no citations. Never invent figures, dates,
parties, or sources; if a value is shown as redacted, say so. You have
{remaining} of {max_steps} steps left including this one; answer as soon as
you have the evidence.

Question: {question}

{transcript}

Respond with JSON only. To call a tool set action and its arguments; to finish
set action to "answer" and fill answer, citations, and refused."""

FORCE_PROMPT = """Your step budget is exhausted. Using only the tool results above, give your
final answer now in the answer schema. Cite chunk_ids from the tool results;
if they do not support an answer, refuse and cite nothing.

Question: {question}

{transcript}

Respond with JSON only: answer (string), citations (chunk_id and quote pairs),
refused (boolean)."""


def _digest(tool: str, result) -> str:
    if tool == "search_corpus":
        return "\n".join(f"[{r['chunk_id']}] {r['text'][:400]}" for r in result)
    if tool == "read_document":
        if "sections" in result:
            return f"sections of {result['doc_id']}: {', '.join(result['sections'][:40])}"
        if "chunks" in result:
            return "\n".join(f"[{c['chunk_id']}] {c['text'][:600]}" for c in result["chunks"])
        return str(result.get("error", result))
    if tool == "cross_reference":
        lines = []
        for hits in result.get("per_document", {}).values():
            for h in hits:
                lines.append(f"[{h['chunk_id']}] {h['text'][:300]}")
        return "\n".join(lines) or "no results"
    return str(result)[:400]


class AgentVariant:
    """Six-step tool loop behind the same variant interface as everything else."""

    name = "agent"

    def __init__(self, toolbox: Toolbox | None = None, backend=None):
        self._toolbox = toolbox
        self._backend = backend or get_backend()
        self.dropped_citations = 0
        self.traces: dict[str, dict] = {}

    def _tools(self) -> Toolbox:
        if self._toolbox is None:
            from corpusgate.retrieval import index
            from corpusgate.retrieval.embed import get_embedder

            self._toolbox = Toolbox(index.get_client(), get_embedder("local"))
        return self._toolbox

    def _run_tool(self, action: str, step: dict):
        toolbox = self._tools()
        if action == "search_corpus":
            return toolbox.search_corpus(step.get("query") or "", k=5)
        if action == "read_document":
            return toolbox.read_document(step.get("doc_id") or "", step.get("section"))
        if action == "cross_reference":
            return toolbox.cross_reference(step.get("query") or "", step.get("doc_ids") or [])
        return {"error": f"unknown action {action!r}"}

    def answer(self, question: dict) -> VariantAnswer:
        transcript_parts: list[str] = []
        citable: list[str] = []
        trace: dict = {"question_id": question.get("id"), "steps": []}
        prompt_tokens = completion_tokens = 0
        final: dict | None = None

        for step_no in range(1, MAX_STEPS + 1):
            transcript = "\n\n".join(transcript_parts) or "(no tool results yet)"
            forced = step_no == MAX_STEPS
            if forced:
                prompt = FORCE_PROMPT.format(question=question["question"], transcript=transcript)
                schema = ANSWER_SCHEMA
            else:
                prompt = STEP_PROMPT.format(
                    tool_search=TOOL_DESCRIPTIONS["search_corpus"],
                    tool_read=TOOL_DESCRIPTIONS["read_document"],
                    tool_xref=TOOL_DESCRIPTIONS["cross_reference"],
                    remaining=MAX_STEPS - step_no + 1,
                    max_steps=MAX_STEPS,
                    question=question["question"],
                    transcript=transcript,
                )
                schema = STEP_SCHEMA
            t0 = time.perf_counter()
            payload, p_tok, c_tok = self._backend.complete(prompt, schema)
            latency_ms = round((time.perf_counter() - t0) * 1000, 1)
            prompt_tokens += p_tok
            completion_tokens += c_tok
            action = "answer" if forced else str(payload.get("action", "answer"))

            if action == "answer" or forced:
                final = _normalize(payload)
                trace["steps"].append(
                    {
                        "step": step_no,
                        "action": "answer",
                        "forced": forced,
                        "latency_ms": latency_ms,
                        "prompt_tokens": p_tok,
                        "completion_tokens": c_tok,
                    }
                )
                break

            result = self._run_tool(action, payload)
            observed = observed_chunk_ids(action, result)
            for chunk_id in sorted(observed):
                if chunk_id not in citable:
                    citable.append(chunk_id)
            digest = _digest(action, result)
            transcript_parts.append(f"step {step_no} {action} result:\n{digest}")
            trace["steps"].append(
                {
                    "step": step_no,
                    "action": action,
                    "args": {
                        k: payload.get(k)
                        for k in ("query", "doc_id", "section", "doc_ids")
                        if payload.get(k)
                    },
                    "observation_digest": digest[:500],
                    "observed_chunk_ids": sorted(observed),
                    "latency_ms": latency_ms,
                    "prompt_tokens": p_tok,
                    "completion_tokens": c_tok,
                }
            )

        assert final is not None
        allowed = set(citable)
        citations = []
        for c in final["citations"]:
            if c["chunk_id"] in allowed:
                citations.append(Citation(chunk_id=c["chunk_id"], quote=c["quote"]))
            else:
                self.dropped_citations += 1
        trace["final"] = {
            "answer": final["answer"],
            "refused": final["refused"],
            "citations": [c.chunk_id for c in citations],
            "dropped_citations": len(final["citations"]) - len(citations),
        }
        if question.get("id"):
            self.traces[question["id"]] = trace
        return VariantAnswer(
            answer=final["answer"],
            citations=citations,
            refused=final["refused"],
            retrieved=citable,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
