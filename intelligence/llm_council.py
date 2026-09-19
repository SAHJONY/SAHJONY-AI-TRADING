"""Safe multi-model council for research and signal adjudication.

This module independently implements the *pattern* of multi-model first opinions,
anonymized peer review, and chairman synthesis. It does not copy source code from
karpathy/llm-council and intentionally contains no broker or order-execution path.

Safety contract:
- disabled by default unless SAHJONY_LLM_COUNCIL_ENABLED=true
- research/shadow use only
- never emits order quantity, notional, broker route, or execution instructions
- council output may inform an existing signal pipeline, but existing hard risk
  controls remain authoritative and may veto any downstream action
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
import os
from typing import Any, Callable, Iterable, Mapping, Sequence


ModelCallable = Callable[[str], str]


@dataclass(frozen=True)
class CouncilConfig:
    enabled: bool = False
    research_only: bool = True
    min_models: int = 3
    max_models: int = 7
    chairman_name: str = "chairman"
    max_prompt_chars: int = 24_000
    max_response_chars: int = 12_000
    max_influence: float = 0.15

    @classmethod
    def from_env(cls) -> "CouncilConfig":
        enabled = os.getenv("SAHJONY_LLM_COUNCIL_ENABLED", "false").lower() == "true"
        return cls(enabled=enabled)


@dataclass(frozen=True)
class CouncilOpinion:
    model: str
    anonymous_id: str
    response: str


@dataclass(frozen=True)
class PeerReview:
    reviewer: str
    ranking: list[str]
    critique: str


@dataclass(frozen=True)
class CouncilResult:
    status: str
    query_hash: str
    opinions: list[CouncilOpinion] = field(default_factory=list)
    reviews: list[PeerReview] = field(default_factory=list)
    synthesis: str = ""
    confidence: float = 0.0
    disagreement: float = 1.0
    permitted_influence: float = 0.0
    research_only: bool = True
    execution_blocked: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CouncilSafetyError(RuntimeError):
    """Raised when the council is used outside its safety contract."""


def _clamp_text(value: str, limit: int) -> str:
    return (value or "")[: max(0, limit)]


def _anon_id(name: str, query_hash: str) -> str:
    digest = hashlib.sha256(f"{query_hash}:{name}".encode()).hexdigest()[:8]
    return f"candidate-{digest}"


def _extract_ranking(text: str, candidates: Iterable[str]) -> list[str]:
    """Best-effort ranking parser with deterministic fallback.

    Reviewers are asked to return candidate IDs. Any IDs they omit are appended in
    lexical order so downstream aggregation remains total and deterministic.
    """
    ids = list(candidates)
    found: list[str] = []
    lower = text.lower()
    for candidate in ids:
        if candidate.lower() in lower and candidate not in found:
            found.append(candidate)
    found.extend(sorted(candidate for candidate in ids if candidate not in found))
    return found


def _aggregate_confidence(reviews: Sequence[PeerReview], candidate_ids: Sequence[str]) -> tuple[float, float]:
    if not reviews or not candidate_ids:
        return 0.0, 1.0

    scores = {candidate: 0.0 for candidate in candidate_ids}
    n = len(candidate_ids)
    for review in reviews:
        for rank, candidate in enumerate(review.ranking):
            if candidate in scores:
                scores[candidate] += n - rank

    values = sorted(scores.values(), reverse=True)
    total = sum(values) or 1.0
    top_share = values[0] / total
    second_share = values[1] / total if len(values) > 1 else 0.0
    margin = max(0.0, min(1.0, top_share - second_share))
    disagreement = max(0.0, min(1.0, 1.0 - margin * 2.0))
    confidence = max(0.0, min(1.0, 1.0 - disagreement))
    return confidence, disagreement


class LLMCouncil:
    """Provider-agnostic council with strict separation from execution.

    `models` maps a stable model name to a callable accepting a prompt and
    returning text. This lets the existing SAHJONY provider layer supply OpenAI,
    Anthropic, Gemini, Grok, OpenRouter, or local models without this module owning
    credentials or networking.
    """

    def __init__(
        self,
        models: Mapping[str, ModelCallable],
        chairman: ModelCallable,
        config: CouncilConfig | None = None,
    ) -> None:
        self.models = dict(models)
        self.chairman = chairman
        self.config = config or CouncilConfig.from_env()

    def _validate(self) -> None:
        if not self.config.enabled:
            raise CouncilSafetyError("LLM Council is disabled by feature flag")
        if not self.config.research_only:
            raise CouncilSafetyError("LLM Council must remain research_only")
        if len(self.models) < self.config.min_models:
            raise CouncilSafetyError("Not enough independent models for council")
        if len(self.models) > self.config.max_models:
            raise CouncilSafetyError("Council exceeds configured model limit")
        if not 0.0 <= self.config.max_influence <= 0.25:
            raise CouncilSafetyError("max_influence exceeds safety envelope")

    def run(self, query: str, context: Mapping[str, Any] | None = None) -> CouncilResult:
        self._validate()
        clean_query = _clamp_text(query.strip(), self.config.max_prompt_chars)
        if not clean_query:
            raise ValueError("query must not be empty")

        query_hash = hashlib.sha256(clean_query.encode()).hexdigest()[:16]
        context_json = json.dumps(context or {}, sort_keys=True, default=str)
        context_json = _clamp_text(context_json, self.config.max_prompt_chars // 2)

        opinion_prompt = (
            "You are one independent research member of a trading-analysis council. "
            "Evaluate the evidence, identify uncertainty, and return analysis only. "
            "Do NOT provide broker instructions, order quantities, leverage, notional, "
            "or executable trade commands. Existing deterministic risk controls are final.\n\n"
            f"Question:\n{clean_query}\n\nContext:\n{context_json}"
        )

        opinions: list[CouncilOpinion] = []
        for model_name, model in self.models.items():
            response = _clamp_text(model(opinion_prompt), self.config.max_response_chars)
            opinions.append(
                CouncilOpinion(
                    model=model_name,
                    anonymous_id=_anon_id(model_name, query_hash),
                    response=response,
                )
            )

        anonymous_blob = "\n\n".join(
            f"{op.anonymous_id}:\n{op.response}" for op in opinions
        )
        candidate_ids = [op.anonymous_id for op in opinions]
        reviews: list[PeerReview] = []

        for reviewer_name, reviewer in self.models.items():
            review_prompt = (
                "You are peer-reviewing anonymized research responses. Rank candidate IDs "
                "from strongest to weakest based on evidence quality, calibration, risk "
                "awareness, and falsifiability. Ignore writing style and do not infer model "
                "identity. Include every candidate ID.\n\n"
                f"Question:\n{clean_query}\n\nCandidates:\n{anonymous_blob}"
            )
            critique = _clamp_text(reviewer(review_prompt), self.config.max_response_chars)
            reviews.append(
                PeerReview(
                    reviewer=reviewer_name,
                    ranking=_extract_ranking(critique, candidate_ids),
                    critique=critique,
                )
            )

        confidence, disagreement = _aggregate_confidence(reviews, candidate_ids)
        review_blob = "\n\n".join(
            f"Reviewer {i + 1} ranking: {', '.join(review.ranking)}\n{review.critique}"
            for i, review in enumerate(reviews)
        )
        synthesis_prompt = (
            "Act as chairman of a trading research council. Synthesize the anonymized opinions "
            "and peer reviews into a concise research conclusion. Explicitly state uncertainty, "
            "key invalidation conditions, and disagreements. Analysis only: never emit order "
            "size, notional, leverage, broker routing, or executable instructions. Existing hard "
            "risk controls remain authoritative.\n\n"
            f"Question:\n{clean_query}\n\nOpinions:\n{anonymous_blob}\n\nReviews:\n{review_blob}"
        )
        synthesis = _clamp_text(self.chairman(synthesis_prompt), self.config.max_response_chars)

        permitted_influence = min(self.config.max_influence, self.config.max_influence * confidence)
        return CouncilResult(
            status="research_complete",
            query_hash=query_hash,
            opinions=opinions,
            reviews=reviews,
            synthesis=synthesis,
            confidence=round(confidence, 4),
            disagreement=round(disagreement, 4),
            permitted_influence=round(permitted_influence, 4),
            research_only=True,
            execution_blocked=True,
            metadata={
                "council_size": len(opinions),
                "chairman": self.config.chairman_name,
                "safety_contract": "no-direct-execution",
            },
        )


def apply_council_tilt(base_score: float, result: CouncilResult, directional_vote: float) -> float:
    """Bounded research-only influence helper.

    The council may slightly tilt an existing normalized score, never create a trade
    by itself. `directional_vote` must be in [-1, 1]. Existing execution/risk gates
    remain outside and downstream of this function.
    """
    if not result.execution_blocked or not result.research_only:
        raise CouncilSafetyError("unsafe council result rejected")
    vote = max(-1.0, min(1.0, float(directional_vote)))
    influence = max(0.0, min(0.25, result.permitted_influence))
    return max(-1.0, min(1.0, float(base_score) + vote * influence))
