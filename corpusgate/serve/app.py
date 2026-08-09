"""The serving API: health, and authenticated /query over the configured variant.

Auth is a bearer token from CORPUSGATE_API_TOKEN; health stays open
so orchestration can probe. Answers return the citation schema
enriched with the actual cited passages fetched from the index, so
the UI renders evidence rather than identifiers. The streaming
endpoint emits status events and then the answer as server-sent
events; per-request latency and token counts ride every response.
"""

import hmac
import json
import os
import time
import uuid
from collections.abc import Callable

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import corpusgate
from corpusgate.serve import metrics


class QueryRequest(BaseModel):
    question: str


def _default_variant_factory():
    from corpusgate.evals.variants import get_variant

    return get_variant(os.environ.get("SERVE_VARIANT", "rag"))


def _default_passage_lookup() -> Callable[[list[str]], dict[str, dict]]:
    from corpusgate.retrieval import index

    client = index.get_client()

    def lookup(chunk_ids: list[str]) -> dict[str, dict]:
        if not chunk_ids:
            return {}
        points = client.retrieve(
            index.COLLECTION,
            ids=[index.point_id(cid) for cid in chunk_ids],
            with_payload=True,
        )
        return {p.payload["chunk_id"]: p.payload for p in points}

    return lookup


def require_token(request: Request) -> None:
    expected = os.environ.get("CORPUSGATE_API_TOKEN")
    if not expected:
        raise HTTPException(503, "CORPUSGATE_API_TOKEN is not configured on the server")
    header = request.headers.get("authorization", "")
    if not hmac.compare_digest(header.encode(), f"Bearer {expected}".encode()):
        raise HTTPException(401, "missing or invalid bearer token")


def create_app() -> FastAPI:
    app = FastAPI(title="CorpusGate API", version=corpusgate.__version__)
    app.state.variant = None
    app.state.variant_factory = _default_variant_factory
    app.state.passage_lookup = None
    app.state.passage_lookup_factory = _default_passage_lookup

    def get_variant_instance():
        if app.state.variant is None:
            app.state.variant = app.state.variant_factory()
        return app.state.variant

    def get_passage_lookup():
        if app.state.passage_lookup is None:
            app.state.passage_lookup = app.state.passage_lookup_factory()
        return app.state.passage_lookup

    @app.get("/health")
    def health() -> dict:
        return {
            "status": "ok",
            "version": corpusgate.__version__,
            "model_backend": os.environ.get("MODEL_BACKEND", "local"),
        }

    def run_query(question: str) -> dict:
        variant = get_variant_instance()
        started = time.perf_counter()
        result = variant.answer({"id": f"req-{uuid.uuid4().hex[:12]}", "question": question})
        latency_ms = round((time.perf_counter() - started) * 1000, 1)
        passages = get_passage_lookup()([c.chunk_id for c in result.citations])
        citations = []
        for c in result.citations:
            payload = passages.get(c.chunk_id, {})
            citations.append(
                {
                    "chunk_id": c.chunk_id,
                    "quote": c.quote,
                    "doc_id": payload.get("doc_id", c.chunk_id.split("#")[0]),
                    "section": payload.get("section", ""),
                    "passage": payload.get("text", ""),
                }
            )
        response = {
            "request_id": uuid.uuid4().hex,
            "answer": result.answer,
            "refused": result.refused,
            "citations": citations,
            "latency_ms": latency_ms,
            "prompt_tokens": result.prompt_tokens,
            "completion_tokens": result.completion_tokens,
        }
        metrics.append_record(
            {
                "request_id": response["request_id"],
                "variant": getattr(variant, "name", "unknown"),
                "backend": os.environ.get("MODEL_BACKEND", "local"),
                "latency_ms": latency_ms,
                "prompt_tokens": result.prompt_tokens,
                "completion_tokens": result.completion_tokens,
                "refused": result.refused,
                "citations": len(citations),
            }
        )
        return response

    @app.get("/metrics", dependencies=[Depends(require_token)])
    def metrics_endpoint() -> dict:
        return metrics.aggregate()

    @app.post("/query", dependencies=[Depends(require_token)])
    def query(body: QueryRequest) -> dict:
        return run_query(body.question)

    @app.post("/query/stream", dependencies=[Depends(require_token)])
    def query_stream(body: QueryRequest) -> StreamingResponse:
        def events():
            yield "event: status\ndata: retrieving and generating\n\n"
            result = run_query(body.question)
            yield f"event: answer\ndata: {json.dumps(result)}\n\n"

        return StreamingResponse(events(), media_type="text/event-stream")

    return app


app = create_app()
