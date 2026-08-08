"""The first real variants: base (no retrieval) and one-shot RAG.

Both answer through the variant interface in the mandatory citation
schema. The RAG variant retrieves top-k chunks, presents them with
their chunk IDs, and instructs the model to answer only from them or
refuse; the base variant gets the question and nothing else, which
is the floor that shows what retrieval buys.

Citations are structural: any citation naming a chunk ID that was
not retrieved is dropped and counted, so a fabricated ID can never
reach the judge dressed as evidence. The ranked retrieved list is
recorded for the mechanical retrieval metrics regardless of what the
model cites.

Backends are pluggable: the api backend uses the pinned model with
structured outputs; the local backend targets the llama.cpp service
from milestone M2's compose plan; the fake backend makes the whole
path testable in CI with no network.
"""

import json
import os
from pathlib import Path

import yaml

from corpusgate.evals.variants import Citation, VariantAnswer

ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "citations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"chunk_id": {"type": "string"}, "quote": {"type": "string"}},
                "required": ["chunk_id", "quote"],
                "additionalProperties": False,
            },
        },
        "refused": {"type": "boolean"},
    },
    "required": ["answer", "citations", "refused"],
    "additionalProperties": False,
}

RAG_PROMPT = """You answer questions about a corpus of commercial contracts.

Use ONLY the contract excerpts below. Every factual claim must be supported by
the excerpts and cited by chunk_id with a short supporting quote. If the
excerpts do not contain the answer, refuse: set refused to true, explain that
the corpus does not support an answer, and cite nothing. Never invent figures,
dates, parties, or sources; if a value is shown as redacted, say so.

Excerpts:
{excerpts}

Question: {question}

Respond with JSON only: answer (string), citations (chunk_id and quote pairs
drawn from the excerpts), refused (boolean)."""

BASE_PROMPT = """You answer questions about a corpus of commercial contracts, but no corpus
excerpts are available to you in this mode. If you cannot support an answer
from provided corpus material, refuse: set refused to true, explain that you
have no corpus evidence, and cite nothing. Never invent figures, dates,
parties, or sources.

Question: {question}

Respond with JSON only: answer (string), citations (empty unless you can cite
provided corpus chunk ids), refused (boolean)."""


def api_model(config_path: str | Path = "configs/models.yaml") -> str:
    return yaml.safe_load(Path(config_path).read_text())["models"]["api_backend"]


class AnthropicAnswerBackend:
    """The api backend: development convenience only, per rule six."""

    def __init__(self, model: str | None = None, max_tokens: int = 1024):
        import anthropic

        self._client = anthropic.Anthropic()
        self.model = model or api_model()
        self.max_tokens = max_tokens

    def complete(self, prompt: str, schema: dict | None = None) -> tuple[dict, int, int]:
        response = self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            thinking={"type": "disabled"},
            output_config={"format": {"type": "json_schema", "schema": schema or ANSWER_SCHEMA}},
            messages=[{"role": "user", "content": prompt}],
        )
        if response.stop_reason == "refusal":
            payload = {"answer": "The request was declined.", "citations": [], "refused": True}
            return payload, response.usage.input_tokens, response.usage.output_tokens
        text = next(block.text for block in response.content if block.type == "text")
        return json.loads(text), response.usage.input_tokens, response.usage.output_tokens


class LocalAnswerBackend:
    """The llama.cpp service backend; the deployment target."""

    def __init__(self, url: str | None = None, max_tokens: int = 1024):
        import httpx

        self._http = httpx.Client(timeout=300)
        self.url = (url or os.environ.get("LLM_URL", "http://localhost:8080")).rstrip("/")
        self.max_tokens = max_tokens

    def complete(self, prompt: str, schema: dict | None = None) -> tuple[dict, int, int]:
        response = self._http.post(
            f"{self.url}/v1/chat/completions",
            json={
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": self.max_tokens,
                "response_format": {"type": "json_object"},
            },
        )
        response.raise_for_status()
        body = response.json()
        text = body["choices"][0]["message"]["content"]
        usage = body.get("usage", {})
        return (
            json.loads(text),
            int(usage.get("prompt_tokens", 0)),
            int(usage.get("completion_tokens", 0)),
        )


def get_backend(kind: str | None = None):
    kind = kind or os.environ.get("MODEL_BACKEND", "local")
    if kind == "api":
        return AnthropicAnswerBackend()
    if kind == "local":
        return LocalAnswerBackend()
    raise ValueError(f"unknown answer backend {kind!r}")


def qdrant_retriever(k: int = 5):
    from corpusgate.retrieval import index
    from corpusgate.retrieval.embed import get_embedder

    client = index.get_client()
    embedder = get_embedder("local")

    def retrieve(question: str) -> list[dict]:
        return index.search(client, embedder, question, k=k)

    return retrieve


def _normalize(payload: dict) -> dict:
    return {
        "answer": str(payload.get("answer", "")),
        "citations": [
            {"chunk_id": str(c.get("chunk_id", "")), "quote": str(c.get("quote", ""))}
            for c in payload.get("citations", [])
            if isinstance(c, dict)
        ],
        "refused": bool(payload.get("refused", False)),
    }


class BaseVariant:
    """No retrieval: what the backend knows without the corpus."""

    name = "base"

    def __init__(self, backend=None):
        self._backend = backend or get_backend()

    def answer(self, question: dict) -> VariantAnswer:
        payload, prompt_tokens, completion_tokens = self._backend.complete(
            BASE_PROMPT.format(question=question["question"])
        )
        payload = _normalize(payload)
        return VariantAnswer(
            answer=payload["answer"],
            citations=[],
            refused=payload["refused"],
            retrieved=[],
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )


class RagVariant:
    """One-shot retrieval, then one answer, citations restricted to retrieved chunks."""

    name = "rag"

    def __init__(self, retriever=None, backend=None, k: int = 5):
        self._retriever = retriever or qdrant_retriever(k)
        self._backend = backend or get_backend()
        self.dropped_citations = 0

    def answer(self, question: dict) -> VariantAnswer:
        retrieved = self._retriever(question["question"])
        excerpts = "\n\n".join(
            f"[{c['chunk_id']}]\n{c['text'][:1200]}" for c in retrieved
        )
        payload, prompt_tokens, completion_tokens = self._backend.complete(
            RAG_PROMPT.format(excerpts=excerpts, question=question["question"])
        )
        payload = _normalize(payload)
        retrieved_ids = [c["chunk_id"] for c in retrieved]
        allowed = set(retrieved_ids)
        citations = []
        for c in payload["citations"]:
            if c["chunk_id"] in allowed:
                citations.append(Citation(chunk_id=c["chunk_id"], quote=c["quote"]))
            else:
                self.dropped_citations += 1
                print(f"dropped fabricated citation {c['chunk_id']!r}")
        return VariantAnswer(
            answer=payload["answer"],
            citations=citations,
            refused=payload["refused"],
            retrieved=retrieved_ids,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
