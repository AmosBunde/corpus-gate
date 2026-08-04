"""The variant interface: the fixed contract between the harness and anything it scores.

A variant is anything that can answer an eval question in the answer
schema: text, citations by chunk ID, and an explicit refusal flag,
plus token usage so cost is comparable across variants. The harness
never knows what is behind the interface, which is what keeps base,
RAG, agent, and fine-tuned scores comparable.

Two built-in variants exist for the harness itself: echo, which
refuses everything and represents the floor, and oracle, which
replays the reference answer with the gold anchors as citations and
represents the ceiling the judge should reward. Both run without any
model or network, so the runner and later the judge are testable in
CI.
"""

from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class Citation:
    chunk_id: str
    quote: str


@dataclass
class VariantAnswer:
    answer: str
    citations: list[Citation] = field(default_factory=list)
    refused: bool = False
    retrieved: list[str] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0


class EchoVariant:
    """Floor variant: refuses every question. No model, no retrieval."""

    name = "echo"

    def answer(self, question: dict) -> VariantAnswer:
        return VariantAnswer(
            answer="No model is behind this variant, so the question cannot be answered.",
            citations=[],
            refused=True,
        )


class OracleVariant:
    """Ceiling variant: replays the reference answer, citing the gold anchors.

    Useful for calibrating the judge: a healthy judge should score the
    oracle near the top of the scale on every non-refusal question.
    """

    name = "oracle"

    def answer(self, question: dict) -> VariantAnswer:
        citations = [
            Citation(chunk_id=anchor, quote=question["reference_answer"][:120])
            for anchor in question["gold_anchors"]
        ]
        return VariantAnswer(
            answer=question["reference_answer"],
            citations=citations,
            refused=question["category"] == "refusal",
            retrieved=list(question["gold_anchors"]),
        )


def _base_variant():
    from corpusgate.evals.rag import BaseVariant

    return BaseVariant()


def _rag_variant():
    from corpusgate.evals.rag import RagVariant

    return RagVariant()


VARIANTS: dict[str, Callable[[], object]] = {
    EchoVariant.name: EchoVariant,
    OracleVariant.name: OracleVariant,
    "base": _base_variant,
    "rag": _rag_variant,
}


def get_variant(name: str):
    """Instantiate a registered variant; unknown names fail with the roster."""
    if name not in VARIANTS:
        known = ", ".join(sorted(VARIANTS))
        raise KeyError(f"unknown variant {name!r}; registered variants: {known}")
    return VARIANTS[name]()
