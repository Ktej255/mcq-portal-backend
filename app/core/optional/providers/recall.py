"""Recall concept-matching + adaptive-hint provider for the Optional platform
(Task 12.3 / 12.4 — Phase 1H, R14.1–R14.7).

Mirrors the inference-gateway / evaluation-provider pattern (interface +
deterministic mock + gateway impl + env-driven selector). Callers (the recall
service) depend on the :class:`RecallProvider` interface only.

Two operations:

* ``match(transcript, concept_checklist, segment_script=None) -> RecallMatchSchema``
  — classify each author-defined concept as ``recalled`` / ``partial`` /
  ``missed`` with own-words evidence, rejecting verbatim echoes of the segment
  script as evidence (anti-gaming, design **Property 5** / R14.7).
* ``hint(missed_concepts, prior_responses) -> HintSchema`` — one adaptive
  Socratic cue toward a missed concept, never revealing the answer (R14.2/R14.4).

The production impl routes through the existing inference gateway using the
strict-JSON builders/parsers in :mod:`app.core.optional.prompts` at LOW
temperature (determinism basis, design **Property 4** / R14.6). The
deterministic mock makes the whole record→score→hint loop demoable offline and
gives the property tests a stable, model-free matcher.

Isolation (Requirement 2 / design Property 9): nothing here imports from or
references GS Geography (``/upsc/geography``) modules.
"""

from __future__ import annotations

import os
import re
from abc import ABC, abstractmethod
from typing import Any, List, Mapping, Optional, Sequence

from app.core.optional.prompts import (
    ConceptClassification,
    HintSchema,
    RecallMatchSchema,
    SchemaValidationError,
    build_hint_request,
    build_recall_match_request,
    parse_hint,
    parse_recall_match,
)


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------
class RecallProvider(ABC):
    """Abstract recall matcher + hinter."""

    name: str = "abstract"

    @abstractmethod
    def match(
        self,
        transcript: str,
        concept_checklist: Sequence[Mapping[str, Any]],
        *,
        segment_script: Optional[str] = None,
    ) -> RecallMatchSchema:
        """Classify each checklist concept against the transcript (R14.1/R14.7)."""
        raise NotImplementedError

    @abstractmethod
    def hint(
        self,
        missed_concepts: Sequence[Any],
        prior_responses: Sequence[str],
    ) -> HintSchema:
        """Produce one adaptive Socratic hint toward a missed concept (R14.2/R14.4)."""
        raise NotImplementedError


def _tokenize(text: str) -> List[str]:
    return [t for t in re.findall(r"[a-z0-9]+", str(text).lower()) if t]


def _normalize(text: str) -> str:
    return " ".join(_tokenize(text))


# ---------------------------------------------------------------------------
# Deterministic mock implementation
# ---------------------------------------------------------------------------
class MockRecallProvider(RecallProvider):
    """Deterministic, dependency-free recall matcher for tests and local/dev.

    Classifies by token overlap between the transcript and each concept text —
    no model, no network, fully reproducible (Property 4). Anti-gaming
    (Property 5): if the transcript merely repeats the segment script verbatim
    or near-verbatim, every concept is marked ``missed`` with
    ``verbatim_echo=True`` so echoing the script never earns recall.
    """

    name = "mock"

    # Overlap thresholds (fraction of a concept's tokens present in the transcript).
    _RECALLED_AT = 0.6
    _PARTIAL_AT = 0.3
    # Transcript/script token-overlap above which we treat the response as a
    # near-verbatim echo of the segment script (anti-gaming).
    _ECHO_AT = 0.85

    def _is_verbatim_echo(self, transcript: str, segment_script: Optional[str]) -> bool:
        if not segment_script:
            return False
        t_norm = _normalize(transcript)
        s_norm = _normalize(segment_script)
        if not t_norm or not s_norm:
            return False
        # Direct containment is the clearest echo signal.
        if s_norm and (s_norm in t_norm or t_norm in s_norm):
            return True
        # Otherwise compare token sets: a transcript that is overwhelmingly the
        # script's own tokens (and adds little of its own) is an echo.
        t_tokens = set(_tokenize(transcript))
        s_tokens = set(_tokenize(segment_script))
        if not t_tokens:
            return False
        shared = len(t_tokens & s_tokens)
        return (shared / len(t_tokens)) >= self._ECHO_AT

    def match(
        self,
        transcript: str,
        concept_checklist: Sequence[Mapping[str, Any]],
        *,
        segment_script: Optional[str] = None,
    ) -> RecallMatchSchema:
        echo = self._is_verbatim_echo(transcript, segment_script)
        transcript_tokens = set(_tokenize(transcript))
        snippet = " ".join(str(transcript).split())[:200]

        concepts: List[ConceptClassification] = []
        for item in concept_checklist:
            concept_text = str(item.get("concept", "")).strip()
            if not concept_text:
                continue

            if echo:
                # Anti-gaming: verbatim echo is never recall evidence (P5).
                concepts.append(
                    ConceptClassification(
                        concept=concept_text,
                        classification="missed",
                        evidence="",
                        verbatim_echo=True,
                    )
                )
                continue

            concept_tokens = set(_tokenize(concept_text))
            if not concept_tokens:
                continue
            overlap = len(concept_tokens & transcript_tokens) / len(concept_tokens)

            if overlap >= self._RECALLED_AT:
                concepts.append(
                    ConceptClassification(
                        concept=concept_text,
                        classification="recalled",
                        evidence=snippet or concept_text,
                    )
                )
            elif overlap >= self._PARTIAL_AT:
                concepts.append(
                    ConceptClassification(
                        concept=concept_text,
                        classification="partial",
                        evidence=snippet or concept_text,
                    )
                )
            else:
                concepts.append(
                    ConceptClassification(
                        concept=concept_text,
                        classification="missed",
                        evidence="",
                    )
                )

        if not concepts:
            # The schema requires at least one concept; surface an empty-checklist
            # call as a single missed placeholder is wrong — instead raise so the
            # caller treats it as a configuration error.
            raise SchemaValidationError("recall match requires a non-empty checklist")
        return RecallMatchSchema(concepts=concepts)

    def hint(
        self,
        missed_concepts: Sequence[Any],
        prior_responses: Sequence[str],
    ) -> HintSchema:
        def _concept_text(c: Any) -> str:
            if isinstance(c, Mapping):
                return str(c.get("concept", "")).strip()
            return str(c).strip()

        target = next((_concept_text(c) for c in missed_concepts if _concept_text(c)), "")
        if not target:
            # Nothing missed — still return a well-formed, non-revealing nudge.
            return HintSchema(
                hint="You've covered the key ideas — can you add one more detail in your own words?",
                target_concept="general",
            )
        # Socratic cue: names the theme to nudge toward (like an offline teacher
        # asking "what about the youthful stage?") without stating the answer.
        return HintSchema(
            hint=(
                f"Think about \"{target}\". What can you recall about it, "
                "in your own words?"
            ),
            target_concept=target,
        )


# ---------------------------------------------------------------------------
# Gateway (Gemini) implementation — via the existing inference gateway
# ---------------------------------------------------------------------------
class GatewayRecallProvider(RecallProvider):
    """Recall matcher/hinter routed through the EXISTING inference gateway.

    Builds the strict-JSON requests with the prompt builders (LOW temperature,
    determinism basis — Property 4) and validates responses with the parsers.
    The gateway is imported lazily so importing this module never requires
    credentials.

    Honest degradation: if the gateway call fails or the output fails strict
    validation, :meth:`match` returns an all-``missed`` classification (score 0,
    an honest "could not assess" rather than a fabricated recall), and
    :meth:`hint` falls back to a safe, non-revealing Socratic nudge.
    """

    name = "gemini"

    def __init__(self, provider_name: str = "gemini"):
        self.provider_name = provider_name

    def _generate(self, request):
        from app.core.inference.gateway import InferenceGateway

        return InferenceGateway.get_provider(self.provider_name).generate(request)

    def match(
        self,
        transcript: str,
        concept_checklist: Sequence[Mapping[str, Any]],
        *,
        segment_script: Optional[str] = None,
    ) -> RecallMatchSchema:
        request = build_recall_match_request(
            transcript, concept_checklist, segment_script=segment_script
        )
        try:
            response = self._generate(request)
            return parse_recall_match(response)
        except (SchemaValidationError, Exception):
            # Honest degradation: classify every concept as missed.
            concepts = [
                ConceptClassification(
                    concept=str(item.get("concept", "")).strip(),
                    classification="missed",
                    evidence="",
                )
                for item in concept_checklist
                if str(item.get("concept", "")).strip()
            ]
            if not concepts:
                raise SchemaValidationError(
                    "recall match requires a non-empty checklist"
                )
            return RecallMatchSchema(concepts=concepts)

    def hint(
        self,
        missed_concepts: Sequence[Any],
        prior_responses: Sequence[str],
    ) -> HintSchema:
        request = build_hint_request(missed_concepts, prior_responses)
        try:
            response = self._generate(request)
            return parse_hint(response)
        except (SchemaValidationError, Exception):
            return MockRecallProvider().hint(missed_concepts, prior_responses)


# ---------------------------------------------------------------------------
# Selector / factory (env-driven, like the inference gateway)
# ---------------------------------------------------------------------------
_PROVIDERS: dict = {}


def get_recall_provider(name: Optional[str] = None) -> RecallProvider:
    """Return a :class:`RecallProvider`, selected by ``name`` or environment.

    Precedence: explicit ``name`` → ``OPTIONAL_RECALL_PROVIDER`` env → ``"mock"``.
    The mock is the safe deterministic default for test/dev. Cached per-name;
    ``ValueError`` for unknown names.
    """
    resolved = (
        name or os.environ.get("OPTIONAL_RECALL_PROVIDER") or "mock"
    ).strip().lower()

    if resolved in _PROVIDERS:
        return _PROVIDERS[resolved]

    if resolved == "mock":
        provider: RecallProvider = MockRecallProvider()
    elif resolved in ("gemini", "gateway"):
        provider = GatewayRecallProvider()
    else:
        raise ValueError(f"Unknown recall provider '{resolved}'")

    _PROVIDERS[resolved] = provider
    return provider


__all__ = [
    "RecallProvider",
    "MockRecallProvider",
    "GatewayRecallProvider",
    "get_recall_provider",
]
