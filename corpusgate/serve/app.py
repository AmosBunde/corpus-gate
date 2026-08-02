"""Minimal serving stub for the compose scaffold: health only.

The full query endpoint with auth, streaming, citation rendering
support, and per-request latency and token cost logging lands in
milestone M5.
"""

import os

from fastapi import FastAPI

import corpusgate

app = FastAPI(title="CorpusGate API", version=corpusgate.__version__)


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "version": corpusgate.__version__,
        "model_backend": os.environ.get("MODEL_BACKEND", "local"),
    }
