"""Pydantic response schemas for the Optional Subjects Platform content API
(Task 6.1 — Read layer backend).

These schemas shape the backend-served syllabus tree and per-topic content so
the frontend ``ReadView`` never reads the legacy frontend TS files (those are
deleted in a later gated task). They cover:

* ``SyllabusTreeOut`` — the subject's papers → sections → topics → subtopics
  tree, each node carrying its ``review_status`` and an ``authored`` flag.
* ``NodeContentOut`` — a syllabus node's reviewed/authored ContentUnit (typed
  blocks, examiner keywords, answer-language phrasing, hidden topics) plus its
  Diagram rows, recursively including child subtopics.

Honesty gate (design Property 8 / R5.4): the ``authored`` flag is True only
when a node has a ContentUnit that is BOTH ``authored=True`` AND
``review_status == REVIEWED`` (and not soft-deleted). When a node is not
authored, ``content`` is ``None`` so the UI shows an honest "not yet authored"
state instead of fabricated content.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Syllabus tree
# ---------------------------------------------------------------------------

class SyllabusNodeOut(BaseModel):
    """A node in the weighted syllabus tree (TOPIC / SUBTOPIC)."""
    node_id: int
    title: str
    node_type: str
    review_status: str
    # Honesty gate: True only when a reviewed+authored ContentUnit exists.
    authored: bool
    weight: float
    display_order: int
    official_phrasing: Optional[str] = None
    children: list["SyllabusNodeOut"] = []


class SyllabusSectionOut(BaseModel):
    section_id: int
    label: Optional[str] = None
    name: str
    display_order: int
    nodes: list[SyllabusNodeOut] = []


class SyllabusPaperOut(BaseModel):
    paper_id: int
    label: str
    name: str
    display_order: int
    sections: list[SyllabusSectionOut] = []


class SyllabusTreeOut(BaseModel):
    slug: str
    name: str
    papers: list[SyllabusPaperOut] = []


# ---------------------------------------------------------------------------
# Topic / subtopic content
# ---------------------------------------------------------------------------

class DiagramOut(BaseModel):
    """A diagram render-slot keyed by its stable ``diagram_id``.

    The actual SVG porting is Task 6.2; this carries only the stable key +
    caption so the frontend can render a placeholder slot now.
    """
    diagram_id: str
    title: Optional[str] = None
    caption: Optional[str] = None
    display_order: int


class ContentUnitOut(BaseModel):
    """A reviewed/authored deep-notes content unit (R5.2)."""
    id: int
    title: Optional[str] = None
    # Typed content blocks (para / points / callout / diagram + topic-overview).
    blocks: Optional[Any] = None
    exam_keywords: Optional[list[str]] = None
    answer_language: Optional[list[str]] = None
    hidden_topics: Optional[Any] = None
    review_status: str
    display_order: int
    diagrams: list[DiagramOut] = []


class NodeContentOut(BaseModel):
    """A syllabus node with its reviewed content + child subtopics (R5.1, R5.2).

    ``authored`` is the honesty gate (design Property 8): when False, ``content``
    is ``None`` and the frontend renders an honest not-yet-authored state.
    """
    node_id: int
    title: str
    node_type: str
    review_status: str
    official_phrasing: Optional[str] = None
    authored: bool
    content: Optional[ContentUnitOut] = None
    children: list["NodeContentOut"] = []


# Resolve self-referential forward refs (Pydantic v2).
SyllabusNodeOut.model_rebuild()
NodeContentOut.model_rebuild()


# ---------------------------------------------------------------------------
# PYQ explorer (Task 7.2 — R6.1/R6.2/R6.3/R6.5)
# ---------------------------------------------------------------------------

class PyqOut(BaseModel):
    """A single student-visible (REVIEWED) previous-year question (R6).

    Only PYQs whose ``review_status == REVIEWED`` are ever serialized into this
    shape; unreviewed/draft questions are gated out server-side (design
    Property 8 / R17.3), so this payload never carries hidden content.
    """
    id: int
    year: int
    paper_label: Optional[str] = None
    section_label: Optional[str] = None
    question_text: str
    marks: Optional[int] = None
    beyond_syllabus: bool
    topic_node_id: Optional[int] = None
    review_status: str


class PyqFacetsOut(BaseModel):
    """Available filter facets over the subject's student-visible PYQ corpus.

    Computed across the whole REVIEWED corpus (independent of the currently
    applied filters) so the UI can render stable year/paper/section controls
    that only ever offer values that actually have data.
    """
    years: list[int] = []
    papers: list[str] = []
    sections: list[str] = []


class PyqFiltersEcho(BaseModel):
    """Echo of the filters actually applied to this response (R6.5)."""
    year: Optional[int] = None
    paper: Optional[str] = None
    section: Optional[str] = None
    sort: str = "year_desc"


class PyqListOut(BaseModel):
    """The filtered, year-sorted PYQ list plus filter facets (R6.1/R6.5)."""
    slug: str
    name: str
    total: int
    filters: PyqFiltersEcho
    facets: PyqFacetsOut
    pyqs: list[PyqOut] = []


# ---------------------------------------------------------------------------
# Topic-wise PYQ grouping (Task 7.3 — R6.4)
# ---------------------------------------------------------------------------

class PyqTopicGroupOut(BaseModel):
    """A syllabus topic node and the student-visible PYQs filed beneath it (R6.4).

    Groups the REVIEWED PYQ corpus under its syllabus topic node so the UI can
    present a topic-wise solving view: pick a topic in the syllabus tree, see
    that topic's PYQs. ``paper_label``/``section_label`` (and their human
    names) locate the node within the syllabus structure so the grouped view
    can be organized paper → section → topic.
    """
    node_id: int
    title: str
    node_type: str
    official_phrasing: Optional[str] = None
    paper_label: Optional[str] = None
    paper_name: Optional[str] = None
    section_label: Optional[str] = None
    section_name: Optional[str] = None
    pyq_count: int
    pyqs: list[PyqOut] = []


class PyqByTopicOut(BaseModel):
    """The subject's student-visible PYQs grouped topic-wise (R6.4).

    Only REVIEWED PYQs are grouped (design Property 8 / R17.3); unreviewed /
    draft questions never appear. Groups are ordered by their position in the
    syllabus structure (paper → section → topic); PYQs within each group are
    year-wise (newest first).
    """
    slug: str
    name: str
    total: int
    group_count: int
    groups: list[PyqTopicGroupOut] = []


# ---------------------------------------------------------------------------
# Per-segment syllabus analysis (Task 7.4 — R4.4 / R4.5)
# ---------------------------------------------------------------------------

class SyllabusTrendPointOut(BaseModel):
    """One entry of the "Trend says" layer for a syllabus segment (R4.5).

    Mirrors the importer's ``syllabus.trendSays`` shape (the topic-overview
    ContentUnit's trend layer): a recurring theme, the examiner insight behind
    it, and how frequently it appears.
    """
    theme: str
    insight: str
    frequency: str


class SyllabusHiddenTopicOut(BaseModel):
    """One "Hidden topic" entry — a theme asked beyond the printed syllabus.

    Mirrors the importer's ``syllabus.hiddenTopics`` / ``HiddenTopic`` shape:
    the hidden theme plus the rationale for why it matters (R4.3 / R4.5).
    """
    topic: str
    why: str


class SyllabusSegmentAnalysisOut(BaseModel):
    """The three-layer analysis for a single syllabus segment (R4.5).

    For one syllabus TOPIC node, surfaces the three layers students see when
    they open a segment:

    * ``official`` — the official printed syllabus phrasing ("Official says").
    * ``trend_says`` — the question trend (theme + insight + frequency).
    * ``hidden_topics`` — themes asked beyond the printed syllabus, each with
      its rationale.

    Honesty gate (design Property 8 / R17.3): a segment is only included when it
    has a reviewed+authored overview unit; unreviewed/draft segments are gated
    out exactly like the rest of the Read layer. Segments are located within the
    syllabus structure via their owning ``paper``/``section`` so the UI can sort
    and group them (R4.4).
    """
    node_id: int
    title: str
    node_type: str
    paper_label: Optional[str] = None
    paper_name: Optional[str] = None
    section_label: Optional[str] = None
    section_name: Optional[str] = None
    official: list[str] = []
    trend_says: list[SyllabusTrendPointOut] = []
    hidden_topics: list[SyllabusHiddenTopicOut] = []


class SyllabusAnalysisOut(BaseModel):
    """The subject's per-segment three-layer syllabus analysis (R4.4 / R4.5).

    Returns one {official, trend_says, hidden_topics} entry per **reviewed**
    syllabus segment, ordered by syllabus position (paper → section → topic).
    Only reviewed+authored segments appear (design Property 8 / R17.3); an empty
    ``segments`` list is the honest "nothing authored yet" signal.
    """
    slug: str
    name: str
    segment_count: int
    segments: list[SyllabusSegmentAnalysisOut] = []


# ---------------------------------------------------------------------------
# Practice board status (Task 8 — R7.1 / R7.2 / R7.3)
# ---------------------------------------------------------------------------

# Per-topic practice status values (R7.3). Derived honestly from the student's
# own AnswerAttempt rows for the topic — never fabricated:
#   * NOT_STARTED  — the student has made no attempts on this topic.
#   * IN_PROGRESS  — attempts exist but none has been EVALUATED yet.
#   * PRACTICED    — at least one attempt has been EVALUATED.
PRACTICE_STATUS_NOT_STARTED = "NOT_STARTED"
PRACTICE_STATUS_IN_PROGRESS = "IN_PROGRESS"
PRACTICE_STATUS_PRACTICED = "PRACTICED"


class PracticeTopicStatusOut(BaseModel):
    """A practice topic node with the current student's practice status (R7.3).

    Organized under the syllabus tree (R7.1). ``authored`` is the honesty gate
    (design Property 8): a topic is practiceable only when it has a
    reviewed+authored ContentUnit. When ``authored`` is False the UI shows the
    shared "not yet authored" state rather than a practice call-to-action.

    The status fields are derived purely from the requesting student's own
    ``AnswerAttempt`` rows for this topic (ownership — design Property 10). With
    no attempts the values are the honest zero-state (``attempt_count == 0``,
    ``last_practiced_at is None``, ``status == NOT_STARTED``).
    """
    node_id: int
    title: str
    node_type: str
    authored: bool
    weight: float
    display_order: int
    attempt_count: int
    # Most recent attempt timestamp (ISO 8601) or None when never practiced.
    last_practiced_at: Optional[str] = None
    status: str


class PracticeSectionOut(BaseModel):
    """A section's practice topics (R7.1)."""
    section_id: int
    label: Optional[str] = None
    name: str
    display_order: int
    topics: list[PracticeTopicStatusOut] = []


class PracticePaperOut(BaseModel):
    """A paper's practice sections (R7.1)."""
    paper_id: int
    label: str
    name: str
    display_order: int
    sections: list[PracticeSectionOut] = []


class PracticeBoardOut(BaseModel):
    """The subject's practice topics organized under the syllabus tree (R7.1).

    Mirrors the syllabus-tree shape (papers → sections → topics) so the
    frontend ``PracticeBoard`` can present practice exactly under the structure
    the student already navigates, and overlays each topic's per-student
    practice status (R7.3). Roll-up counters (``authored_topics`` /
    ``practiced_topics``) summarize progress honestly across the board.
    """
    slug: str
    name: str
    total_topics: int
    authored_topics: int
    practiced_topics: int
    papers: list[PracticePaperOut] = []


# ---------------------------------------------------------------------------
# Speak-to-fill transcription (Task 9.2 — R8.2 / R8.3 / R8.4 / R20.3)
# ---------------------------------------------------------------------------

# Confidence gate (design Property 7 / R8.4 / R20.3). When the STT provider's
# overall transcript confidence is below this threshold, the transcript is NOT
# silently committed: the API flags ``low_confidence`` so the UI routes the
# student through an explicit review/correct step before the text fills the
# answer segment. 0.6 is a deliberately conservative midpoint — high-confidence
# mock/real transcripts (~0.95) pass straight through; genuinely uncertain ones
# (accent, noise) are surfaced for human confirmation rather than trusted blind.
STT_CONFIDENCE_THRESHOLD = 0.6


class SttSegmentOut(BaseModel):
    """A contiguous transcribed span with timing + per-segment confidence.

    Mirrors ``app.core.optional.providers.stt.SttSegment`` (timings in seconds,
    ``confidence`` normalised to ``[0, 1]``).
    """
    text: str
    start: float
    end: float
    confidence: float


class TranscriptionOut(BaseModel):
    """A speak-to-fill transcription result (R8.2/R8.3/R8.4/R20.3).

    Returns the provider's normalised transcript plus the confidence-gating
    signal the UI needs to honour the review/correct contract:

    * ``text`` — the transcript that, once accepted, becomes part of the draft
      that will be evaluated (R8.3).
    * ``confidence`` — overall transcript confidence in ``[0, 1]``.
    * ``threshold`` — the gating threshold (``STT_CONFIDENCE_THRESHOLD``).
    * ``low_confidence`` — True iff ``confidence < threshold``; when True the UI
      must show a review/correct step before the transcript fills the segment
      (R8.4 / R20.3 / design Property 7) rather than committing it silently.
    * ``provider`` — which STT backend produced this (mock by default in
      dev/test; a configured Whisper backend in production).
    * ``segments`` — per-segment breakdown for finer-grained review.
    """
    text: str
    confidence: float
    threshold: float
    low_confidence: bool
    provider: str
    segments: list[SttSegmentOut] = []


# ---------------------------------------------------------------------------
# Handwritten-image OCR (Task 9.3 — R9.1 / R9.3 / R20.1)
# ---------------------------------------------------------------------------

# Confidence gate (design Property 7 / R9.3 / R20.1). When the OCR provider's
# overall extraction confidence is below this threshold, the extracted text is
# NOT silently committed to the answer: the API flags ``low_confidence`` so the
# UI informs the student and offers a fallback to review/correct the text, type
# instead, or re-upload — never a silent bad OCR result. 0.6 mirrors the STT
# gate: a deterministic mock (~0.92) passes straight through, while genuinely
# uncertain handwriting extractions are surfaced for human confirmation.
OCR_CONFIDENCE_THRESHOLD = 0.6


class OcrBlockOut(BaseModel):
    """A detected text block/region within the uploaded image.

    Mirrors ``app.core.optional.providers.ocr.OcrBlock``: ``confidence`` is
    normalised to ``[0, 1]`` and ``bbox`` is an optional normalised
    ``[x0, y0, x1, y1]`` box (fractions of width/height).
    """
    text: str
    confidence: float
    bbox: Optional[list[float]] = None


class HandwritingOcrOut(BaseModel):
    """A handwritten-image OCR result (R9.1/R9.3/R20.1).

    Returns the provider's normalised extraction plus the confidence-gating
    signal the UI needs to honour the low-confidence fallback contract:

    * ``text`` — the transcribed handwriting that, once accepted, feeds the
      draft that will be evaluated (R9.1). Evaluation itself is Task 9.4.
    * ``confidence`` — overall extraction confidence in ``[0, 1]``.
    * ``threshold`` — the gating threshold (``OCR_CONFIDENCE_THRESHOLD``).
    * ``low_confidence`` — True iff ``confidence < threshold``; when True the UI
      must inform the student and offer a review/correct / type / re-upload
      fallback before the text fills the answer (R9.3 / R20.1 / design
      Property 7) rather than committing it silently.
    * ``provider`` — which OCR backend produced this (mock by default in
      dev/test; Gemini-Vision via the shared gateway in production).
    * ``blocks`` — per-region breakdown for finer-grained review.
    """
    text: str
    confidence: float
    threshold: float
    low_confidence: bool
    provider: str
    blocks: list[OcrBlockOut] = []


# ---------------------------------------------------------------------------
# Answer evaluation (Task 9.4 — R9.2 / R9.4 / R9.5)
# ---------------------------------------------------------------------------

# Allowed answer-composition modes (mirrors student_models.AnswerModeEnum).
ANSWER_MODE_TYPED = "TYPED"
ANSWER_MODE_SPOKEN = "SPOKEN"
ANSWER_MODE_HANDWRITTEN = "HANDWRITTEN"
ANSWER_MODES = (ANSWER_MODE_TYPED, ANSWER_MODE_SPOKEN, ANSWER_MODE_HANDWRITTEN)


class AnswerSubmitIn(BaseModel):
    """A student's answer draft submitted for evaluation (R9.2).

    Carries the three-part typed composition (``intro``/``body``/``conclusion``,
    R8.1) and/or a combined ``raw_text`` (used for spoken/handwritten drafts once
    transcribed/extracted). The prompt context (``topic_node_id`` / ``pyq_id`` /
    ``question_text``) lets the evaluator build a topic-aware rubric and lets the
    attempt be filed under the right syllabus topic (practice/progress).

    Confidence gating (design Property 7 / R20.1 / R20.3): for spoken/handwritten
    drafts the originating provider confidence (``stt_confidence`` /
    ``ocr_confidence``) is passed through. When it is below the relevant
    threshold and the student has NOT explicitly reviewed it
    (``confidence_acknowledged`` is False), the endpoint refuses to auto-evaluate
    and asks for a review/correct step instead of grading a shaky input.
    """

    model_config = {"extra": "forbid"}

    mode: str
    intro_text: Optional[str] = None
    body_text: Optional[str] = None
    conclusion_text: Optional[str] = None
    raw_text: Optional[str] = None
    topic_node_id: Optional[int] = None
    question_text: Optional[str] = None
    pyq_id: Optional[int] = None
    stt_confidence: Optional[float] = None
    ocr_confidence: Optional[float] = None
    source_media_ref: Optional[str] = None
    # P7: student has reviewed/confirmed a low-confidence transcript/extraction.
    confidence_acknowledged: bool = False


class EvaluationSectionOut(BaseModel):
    """Feedback for one produced evaluation-report section (R9.2)."""
    feedback: str
    score: Optional[float] = None


class EvaluationReportOut(BaseModel):
    """A persisted, student-visible evaluation report (R9.2/R9.4/R9.5).

    ``is_complete`` is True only when ``incomplete_sections`` is empty (design
    Property 6). When the model could not produce a section it appears in
    ``incomplete_sections`` and the report is honestly marked incomplete — never
    presented as complete.
    """
    report_id: Optional[int] = None
    attempt_id: int
    sections: dict[str, EvaluationSectionOut] = {}
    incomplete_sections: list[str] = []
    is_complete: bool
    overall_score: Optional[float] = None


class AnswerEvaluationOut(BaseModel):
    """The result of submitting an answer for evaluation (R9.2/R9.4/R9.5).

    Two honest outcomes:

    * **Evaluated** — ``review_required`` is False and ``report`` carries the
      (possibly incomplete) evaluation report. The attempt + report are
      persisted (R9.5).
    * **Needs review** — ``review_required`` is True (and ``low_confidence`` is
      True): the spoken/handwritten input fell below the confidence threshold
      and was not explicitly reviewed, so it was NOT auto-graded (design
      Property 7). The draft is retained as a DRAFT attempt; ``report`` is None
      and ``message`` explains the review/correct step.
    """
    attempt_id: int
    mode: str
    status: str
    review_required: bool
    low_confidence: bool
    report: Optional[EvaluationReportOut] = None
    message: Optional[str] = None


# ---------------------------------------------------------------------------
# Gap / progress (Task 11 — R12.1 / R12.2 / R12.3 / R12.4)
# ---------------------------------------------------------------------------

# Tracked-activity event types that mark a syllabus node "covered" (R12.2).
# Mirrors student_models.ProgressEventTypeEnum.
PROGRESS_EVENT_READ_COMPLETE = "READ_COMPLETE"
PROGRESS_EVENT_PRACTICE_PASS = "PRACTICE_PASS"
PROGRESS_EVENT_RECALL_THRESHOLD = "RECALL_THRESHOLD"
PROGRESS_EVENT_TYPES = (
    PROGRESS_EVENT_READ_COMPLETE,
    PROGRESS_EVENT_PRACTICE_PASS,
    PROGRESS_EVENT_RECALL_THRESHOLD,
)


class ProgressEventIn(BaseModel):
    """A tracked-activity event recorded against a syllabus node (R12.2).

    Recording an event of any qualifying ``event_type`` against a node marks
    that node "covered" for the requesting student, advancing the weighted
    coverage figure. ``value`` is an optional measured score (e.g. a practice
    or recall score) retained for auditing/thresholding; ``metadata`` is an
    optional free-form payload.
    """

    model_config = {"extra": "forbid"}

    syllabus_node_id: int
    event_type: str
    value: Optional[float] = None
    metadata: Optional[dict] = None


class GapPaperOut(BaseModel):
    """Per-paper coverage breakdown for the gap panel (R12.3)."""
    paper_id: int
    label: str
    name: str
    display_order: int
    covered_percent: float
    remaining_percent: float
    total_nodes: int
    covered_nodes: int


class GapPanelOut(BaseModel):
    """The subject's weighted coverage for the requesting student (R12.3/R12.4).

    ``covered_percent`` is ``Σ weight(covered nodes) / Σ weight(all nodes) × 100``
    over the subject's weighted syllabus tree (design Property 2);
    ``remaining_percent`` is ``100 − covered_percent`` (the two always sum to
    100). The values are derived purely from the requesting student's own
    progress events (ownership — design Property 10); with no activity the
    honest zero-state is ``covered_percent == 0`` / ``remaining_percent == 100``.
    """
    slug: str
    name: str
    covered_percent: float
    remaining_percent: float
    total_nodes: int
    covered_nodes: int
    papers: list[GapPaperOut] = []


# ---------------------------------------------------------------------------
# Recall-LMS (Task 12 — R13 / R14 / R20)
# ---------------------------------------------------------------------------

class RecallSegmentOut(BaseModel):
    """A video segment of a subject's lesson (R13.1).

    The author-defined concept checklist itself is NOT exposed here — revealing
    it would defeat recall; only the ``concept_count`` is surfaced. The matched/
    missed concepts are returned as feedback after the student attempts a recall.
    """
    segment_id: int
    subject_id: int
    title: str
    segment_order: int
    video_ref: Optional[str] = None
    duration_seconds: Optional[int] = None
    concept_count: int


class RecallSegmentListOut(BaseModel):
    """The subject's ordered video segments for the Recall-LMS (R13.1).

    An empty ``segments`` list is the honest "no recall lessons authored yet"
    state — recall content (video + reviewed concept checklists) is authored
    separately and is not fabricated.
    """
    slug: str
    name: str
    total: int
    segments: list[RecallSegmentOut] = []


class RecallMatchedConceptOut(BaseModel):
    """A credited concept in the recall explanation (R14.5)."""
    concept: str
    status: str  # "recalled" | "partial"
    evidence: str = ""


class RecallTurnResultOut(BaseModel):
    """The result of one recall turn (R14.1/R14.3/R14.5/R20.4).

    ``recall_score`` is the cumulative session score in ``[0, 1]`` after this
    turn; ``recall_percent`` is the same as 0–100. ``matched`` / ``missed`` are
    the explainability payload (R14.5). When the score is below 100% a Socratic
    ``hint`` toward a ``hint_target`` missed concept is included (R14.2/R14.4).
    ``stt_low_confidence`` flags an uncertain transcript (R20.3) — the student
    can simply speak again.
    """
    session_id: int
    turn_order: int
    transcript: str
    stt_confidence: float
    stt_low_confidence: bool
    recall_score: float
    recall_percent: float
    matched: list[RecallMatchedConceptOut] = []
    missed: list[str] = []
    hint: Optional[str] = None
    hint_target: Optional[str] = None
    complete: bool = False


class RecallSessionStateOut(BaseModel):
    """A recall session with its ordered turns (R13.5 / R15 reload-on-return)."""
    session_id: int
    segment_id: int
    status: str
    recall_score: float
    recall_percent: float
    turns: list[RecallTurnResultOut] = []


# ---------------------------------------------------------------------------
# Subject selection persistence (Task 13.1 — R1.3 / R15)
# ---------------------------------------------------------------------------

class SubjectSelectionIn(BaseModel):
    """A request to set the student's active optional subject (R1.3)."""

    model_config = {"extra": "forbid"}

    slug: str


class SubjectSelectionOut(BaseModel):
    """The student's currently selected optional subject (R1.3 / R15).

    ``selected`` is False (and the other fields null) when the student has not
    chosen a subject yet — the honest "none selected" state, persisted and
    reloaded per student from the backend rather than only client storage.
    """
    selected: bool
    slug: Optional[str] = None
    name: Optional[str] = None
    subject_id: Optional[int] = None
    selected_at: Optional[str] = None


# ---------------------------------------------------------------------------
# Entitlement seam (Task 13.2 — R16.1 / R16.2 / R16.3)
# ---------------------------------------------------------------------------

class AccessOut(BaseModel):
    """The entitlement decision for a subject + student (R16).

    ``allowed`` gates access; when False the UI must restrict the premium
    content and present ``upgrade_path`` (R16.2). ``premium`` marks whether the
    subject is designated premium at all. The seam returns a safe, configurable
    default until the real entitlement engine is wired (design "Entitlement
    seam"), so wiring the engine later is config, not refactor.
    """
    slug: str
    allowed: bool
    premium: bool
    reason: str
    upgrade_path: Optional[str] = None


# ---------------------------------------------------------------------------
# Geography Mapping module (Task 10 — R10)
# ---------------------------------------------------------------------------

class MapLocationOut(BaseModel):
    """A clickable map location with UPSC-style detail (R10.3).

    Only reviewed locations are ever serialized here (design Property 8); the
    ``detail`` is the 3–4 line "what to know" text shown when the student opens
    the location.
    """
    id: int
    name: str
    category: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    detail: Optional[str] = None
    display_order: int


class MapQuestionOut(BaseModel):
    """A student-visible (REVIEWED) previous-year map-based question (R10.1)."""
    id: int
    year: int
    category: str
    question_text: str
    marks: Optional[int] = None
    beyond_syllabus: bool
    location_id: Optional[int] = None


class MapCategoryGroupOut(BaseModel):
    """A feature category (river / plateau / plain / …) with its map content (R10.2)."""
    category: str
    location_count: int
    question_count: int
    locations: list[MapLocationOut] = []
    questions: list[MapQuestionOut] = []


class MappingOut(BaseModel):
    """The subject's reviewed mapping content organized category-wise (R10).

    Only ``REVIEWED`` locations/questions appear (design Property 8 / R17.3);
    an empty ``categories`` list is the honest "no reviewed mapping content yet"
    signal — draft/seeded mapping stays gated until reviewed for UPSC accuracy.
    """
    slug: str
    name: str
    category_count: int
    location_count: int
    question_count: int
    categories: list[MapCategoryGroupOut] = []


# ---------------------------------------------------------------------------
# Per-subject framework (Task 15 — R11 / R19)
# ---------------------------------------------------------------------------

class SubjectPaperShapeOut(BaseModel):
    """The papers/sections shape a subject declares (R11.1)."""
    label: str
    sections: list[str] = []


class SubjectConfigOut(BaseModel):
    """The DB-backed per-subject configuration (design "Per-subject framework").

    Declares the subject's ``papers``/``sections`` shape, the enabled feature
    modules (``features`` — e.g. ``read``, ``pyq``, ``practice``, ``answer``,
    ``mapping``, ``diagrams``, ``gap``, ``recall``, ``currentAffairs``) and
    content availability (``is_complete`` + ``completeness_status``). The
    frontend mounts subject-specific features by this config (``SubjectFeatureSlot``)
    so adding a subject in Phase 2 is content + config, not new architecture
    (R11.1, R11.2, R19.1).
    """
    slug: str
    name: str
    is_complete: bool
    features: list[str] = []
    papers: list[SubjectPaperShapeOut] = []
    completeness_status: Optional[dict] = None


# ---------------------------------------------------------------------------
# Content review workflow (Task 16.1 — R17.1 / R17.2 / R17.3 / R17.4)
# ---------------------------------------------------------------------------

# Review-gated entity kinds an author/founder can transition.
REVIEW_KIND_CONTENT_UNIT = "content-unit"
REVIEW_KIND_PYQ = "pyq"
REVIEW_KIND_MAP_LOCATION = "map-location"
REVIEW_KIND_MAP_QUESTION = "map-question"
REVIEW_KIND_CURRENT_AFFAIRS = "current-affairs"
REVIEW_KINDS = (
    REVIEW_KIND_CONTENT_UNIT,
    REVIEW_KIND_PYQ,
    REVIEW_KIND_MAP_LOCATION,
    REVIEW_KIND_MAP_QUESTION,
    REVIEW_KIND_CURRENT_AFFAIRS,
)

# Allowed review states (mirror OptionalReviewStatusEnum).
REVIEW_STATUS_VALUES = ("UNREVIEWED", "IN_REVIEW", "REVIEWED")


class ReviewSourceIn(BaseModel):
    """An authoritative source to attach to a content unit on review (R17.1/R17.4)."""

    model_config = {"extra": "forbid"}

    title: str
    citation: Optional[str] = None
    url: Optional[str] = None
    source_type: Optional[str] = None


class ReviewTransitionIn(BaseModel):
    """A request to transition a review-gated entity's status (R17.2/R17.3).

    Setting ``review_status="REVIEWED"`` publishes the entity to students. For a
    content unit, ``authored`` may be set and an authoritative ``source`` may be
    recorded in the same call (R17.1/R17.4) — reviewing without a source is
    discouraged but allowed for already-sourced units.
    """

    model_config = {"extra": "forbid"}

    review_status: str
    authored: Optional[bool] = None
    source: Optional[ReviewSourceIn] = None


class ReviewQueueItemOut(BaseModel):
    """A pending (not-yet-reviewed) item in the review queue."""
    kind: str
    id: int
    label: str
    review_status: str
    extra: Optional[str] = None


class ReviewQueueOut(BaseModel):
    """The subject's pending review queue, grouped by counts (R17.2/R17.3).

    Lists items that are NOT yet ``REVIEWED`` (UNREVIEWED / IN_REVIEW) so an
    author/founder can see exactly what is gated from students and publish it.
    """
    slug: str
    name: str
    total_pending: int
    counts: dict[str, int] = {}
    items: list[ReviewQueueItemOut] = []


class ReviewResultOut(BaseModel):
    """The outcome of a review transition."""
    kind: str
    id: int
    review_status: str
    authored: Optional[bool] = None
    source_recorded: bool = False


# ---------------------------------------------------------------------------
# Per-subject completeness surface (Task 16.2 — R3.5 / R19.3)
# ---------------------------------------------------------------------------

class CompletenessFeatureOut(BaseModel):
    """Per-feature availability for the subject's completeness surface."""
    feature: str
    available: bool


class SubjectCompletenessOut(BaseModel):
    """A student-facing, backend-derived completeness status for a subject (R3.5/R19.3).

    Honest counts from the DB: how many topics/content units are reviewed vs
    total, which feature modules actually have student-visible (REVIEWED)
    content, and an overall status label. This replaces guessing from a static
    catalog — a subject is only "complete" when its content genuinely exists and
    is reviewed.
    """
    slug: str
    name: str
    is_complete: bool
    status_label: str
    reviewed_topics: int
    total_topics: int
    reviewed_content_units: int
    total_content_units: int
    reviewed_pyqs: int
    features: list[CompletenessFeatureOut] = []


# ---------------------------------------------------------------------------
# Subject-specific Current-Affairs feature (Task 17.1 — R11.4 / R19.2)
# ---------------------------------------------------------------------------

class CurrentAffairsItemOut(BaseModel):
    """A student-visible (REVIEWED) current-affairs item (R11.4)."""
    id: int
    title: str
    topic: Optional[str] = None
    summary: Optional[str] = None
    source_url: Optional[str] = None
    published_on: Optional[str] = None
    display_order: int


class CurrentAffairsFeedOut(BaseModel):
    """The subject's reviewed current-affairs feed, newest first (R11.4).

    Only ``REVIEWED`` items appear (design Property 8); an empty ``items`` list
    is the honest "no reviewed current affairs yet" signal — draft items stay
    gated until reviewed.
    """
    slug: str
    name: str
    total: int
    topics: list[str] = []
    items: list[CurrentAffairsItemOut] = []


# ---------------------------------------------------------------------------
# Subject content upload — syllabus + PYQs (Task 17.2 enabler — R19.1/R19.2)
# ---------------------------------------------------------------------------

class ImportSubtopicIn(BaseModel):
    title: str
    official_phrasing: Optional[str] = None


class ImportTopicIn(BaseModel):
    title: str
    official_phrasing: Optional[str] = None
    subtopics: list[ImportSubtopicIn] = []


class ImportSectionIn(BaseModel):
    # ``label`` is SECTION_A / SECTION_B, or null (e.g. Paper II single section).
    label: Optional[str] = None
    name: str
    topics: list[ImportTopicIn] = []


class ImportPaperIn(BaseModel):
    label: str  # PAPER_I / PAPER_II
    name: Optional[str] = None
    sections: list[ImportSectionIn] = []


class ImportPyqIn(BaseModel):
    year: int
    paper: str  # PAPER_I / PAPER_II
    section: Optional[str] = None
    topic_title: Optional[str] = None
    question: str
    marks: Optional[int] = None
    beyond_syllabus: bool = False


class SubjectImportIn(BaseModel):
    """A founder/author upload of a subject's syllabus structure + PYQs.

    Ingested as **gated draft** (UNREVIEWED) — hidden from students until the
    founder reviews and publishes it via the review workflow. Deep Read notes
    are authored separately later; this seeds the navigable skeleton + PYQ
    corpus (R19.1/R19.2).
    """
    slug: str
    name: str
    description: Optional[str] = None
    features: Optional[list[str]] = None
    display_order: Optional[int] = 0
    papers: list[ImportPaperIn] = []
    pyqs: list[ImportPyqIn] = []


class SubjectImportResultOut(BaseModel):
    """Counts report from a subject content upload."""
    slug: str
    review_status: str
    counts: dict[str, int] = {}


__all__ = [
    "SyllabusNodeOut",
    "SyllabusSectionOut",
    "SyllabusPaperOut",
    "SyllabusTreeOut",
    "DiagramOut",
    "ContentUnitOut",
    "NodeContentOut",
    "PyqOut",
    "PyqFacetsOut",
    "PyqFiltersEcho",
    "PyqListOut",
    "PyqTopicGroupOut",
    "PyqByTopicOut",
    "SyllabusTrendPointOut",
    "SyllabusHiddenTopicOut",
    "SyllabusSegmentAnalysisOut",
    "SyllabusAnalysisOut",
    "PracticeTopicStatusOut",
    "PracticeSectionOut",
    "PracticePaperOut",
    "PracticeBoardOut",
    "PRACTICE_STATUS_NOT_STARTED",
    "PRACTICE_STATUS_IN_PROGRESS",
    "PRACTICE_STATUS_PRACTICED",
    "STT_CONFIDENCE_THRESHOLD",
    "SttSegmentOut",
    "TranscriptionOut",
    "OCR_CONFIDENCE_THRESHOLD",
    "OcrBlockOut",
    "HandwritingOcrOut",
    "ANSWER_MODE_TYPED",
    "ANSWER_MODE_SPOKEN",
    "ANSWER_MODE_HANDWRITTEN",
    "ANSWER_MODES",
    "AnswerSubmitIn",
    "EvaluationSectionOut",
    "EvaluationReportOut",
    "AnswerEvaluationOut",
    "PROGRESS_EVENT_READ_COMPLETE",
    "PROGRESS_EVENT_PRACTICE_PASS",
    "PROGRESS_EVENT_RECALL_THRESHOLD",
    "PROGRESS_EVENT_TYPES",
    "ProgressEventIn",
    "GapPaperOut",
    "GapPanelOut",
    "RecallSegmentOut",
    "RecallSegmentListOut",
    "RecallMatchedConceptOut",
    "RecallTurnResultOut",
    "RecallSessionStateOut",
    "SubjectSelectionIn",
    "SubjectSelectionOut",
    "AccessOut",
    "MapLocationOut",
    "MapQuestionOut",
    "MapCategoryGroupOut",
    "MappingOut",
    "SubjectPaperShapeOut",
    "SubjectConfigOut",
    "REVIEW_KIND_CONTENT_UNIT",
    "REVIEW_KIND_PYQ",
    "REVIEW_KIND_MAP_LOCATION",
    "REVIEW_KIND_MAP_QUESTION",
    "REVIEW_KINDS",
    "REVIEW_STATUS_VALUES",
    "ReviewSourceIn",
    "ReviewTransitionIn",
    "ReviewQueueItemOut",
    "ReviewQueueOut",
    "ReviewResultOut",
    "CompletenessFeatureOut",
    "SubjectCompletenessOut",
    "REVIEW_KIND_CURRENT_AFFAIRS",
    "CurrentAffairsItemOut",
    "CurrentAffairsFeedOut",
    "ImportSubtopicIn",
    "ImportTopicIn",
    "ImportSectionIn",
    "ImportPaperIn",
    "ImportPyqIn",
    "SubjectImportIn",
    "SubjectImportResultOut",
]
