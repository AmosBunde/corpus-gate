"""Skeleton tests: the package imports and every subpackage states its purpose."""

import importlib

import corpusgate

SUBPACKAGES = ["ingest", "retrieval", "agent", "llm", "evals", "finetune", "serve"]


def test_version() -> None:
    assert corpusgate.__version__ == "0.1.0"


def test_every_subpackage_imports_and_is_documented() -> None:
    for name in SUBPACKAGES:
        module = importlib.import_module(f"corpusgate.{name}")
        assert module.__doc__, f"corpusgate.{name} must state its purpose and milestone"
