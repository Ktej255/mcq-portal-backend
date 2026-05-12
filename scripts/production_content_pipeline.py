"""
MCQ Production Content Pipeline
================================
Task A1: Normalize raw MCQ data
Task A2: Deterministic option reshuffling (question & correct answer semantics PRESERVED)
Task A3: Batch structure creation (8 batches × 50 MCQs per subject)
Task A4: Database ingestion
Task A5: Post-ingestion verification summary

Usage:
    python scripts/production_content_pipeline.py --data-file data/mcqs.json [--dry-run] [--reshuffle-seed 42]

JSON input format expected:
[
  {
    "subject": "Environment",
    "topic": "Ecology",
    "text_en": "...",
    "text_hi": "...",
    "options_en": {"A": "...", "B": "...", "C": "...", "D": "..."},
    "options_hi": {"A": "...", "B": "...", "C": "...", "D": "..."},
    "correct_option": "A",
    "explanation_en": "...",
    "explanation_hi": "...",
    "difficulty": "MEDIUM"
  },
  ...
]
"""

import os
import sys
import json
import random
import argparse
import unicodedata
from copy import deepcopy
from collections import defaultdict
from datetime import datetime, timezone

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import SessionLocal
from app.models.domain import Subject, Topic, Test, Question

# ─────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────

SUBJECTS = ["Environment", "Polity", "History", "Science", "Economy", "Geography"]
BATCHES_PER_SUBJECT = 8
MCQS_PER_BATCH = 50
TOTAL_PER_SUBJECT = BATCHES_PER_SUBJECT * MCQS_PER_BATCH  # 400
OPTION_KEYS = ["A", "B", "C", "D"]

TEST_DURATION_MINUTES = 60
CORRECT_MARKS = 2.0
NEGATIVE_MARKING_VALUE = 0.66

# ─────────────────────────────────────────────────────────────
# TASK A1 — NORMALIZATION
# ─────────────────────────────────────────────────────────────

def normalize_text(text: str) -> str:
    """Normalize whitespace, unicode, and common encoding artifacts."""
    if not text:
        return text
    # Unicode normalization (handles Hindi/Devanagari correctly)
    text = unicodedata.normalize("NFC", text)
    # Collapse multiple whitespace to single space
    text = " ".join(text.split())
    return text.strip()


def normalize_options(options: dict) -> dict:
    """Normalize all option values."""
    return {k: normalize_text(v) for k, v in options.items()}


def validate_mcq(mcq: dict, idx: int) -> list[str]:
    """Validate a single MCQ. Returns list of error strings (empty = valid)."""
    errors = []
    opts = mcq.get("options_en", {})

    if not mcq.get("text_en", "").strip():
        errors.append(f"[{idx}] Missing English question text")
    if len(opts) != 4:
        errors.append(f"[{idx}] options_en must have exactly 4 keys, got {len(opts)}")
    if set(opts.keys()) != {"A", "B", "C", "D"}:
        errors.append(f"[{idx}] options_en keys must be A/B/C/D")
    if mcq.get("correct_option") not in OPTION_KEYS:
        errors.append(f"[{idx}] correct_option '{mcq.get('correct_option')}' is invalid")
    if not mcq.get("subject", "").strip():
        errors.append(f"[{idx}] Missing subject")
    if mcq.get("subject") not in SUBJECTS:
        errors.append(f"[{idx}] Unknown subject '{mcq.get('subject')}'")

    return errors


def normalize_mcq(mcq: dict) -> dict:
    """Apply all normalization rules to a single MCQ dict."""
    mcq = deepcopy(mcq)
    mcq["text_en"] = normalize_text(mcq.get("text_en", ""))
    mcq["text_hi"] = normalize_text(mcq.get("text_hi", ""))
    mcq["options_en"] = normalize_options(mcq.get("options_en", {}))
    if mcq.get("options_hi"):
        mcq["options_hi"] = normalize_options(mcq["options_hi"])
    mcq["explanation_en"] = normalize_text(mcq.get("explanation_en", ""))
    mcq["explanation_hi"] = normalize_text(mcq.get("explanation_hi", ""))
    mcq["difficulty"] = mcq.get("difficulty", "MEDIUM").upper()
    return mcq


# ─────────────────────────────────────────────────────────────
# TASK A2 — DETERMINISTIC OPTION RESHUFFLING
# ─────────────────────────────────────────────────────────────

def reshuffle_options(mcq: dict, seed: int) -> dict:
    """
    Deterministically reshuffle option order for a single MCQ.
    
    GUARANTEES:
    - Question text is unchanged
    - The semantic correct answer is unchanged (only its label changes)
    - correct_option is updated to reflect the new label
    - Both EN and HI options are reshuffled in sync
    - explanation remains correct (text unchanged)
    """
    mcq = deepcopy(mcq)
    rng = random.Random(seed)

    original_correct_key = mcq["correct_option"]  # e.g. "A"
    original_correct_value_en = mcq["options_en"][original_correct_key]
    original_correct_value_hi = (
        mcq["options_hi"].get(original_correct_key) if mcq.get("options_hi") else None
    )

    # Shuffle the key order
    shuffled_keys = OPTION_KEYS[:]
    rng.shuffle(shuffled_keys)

    new_options_en = {}
    new_options_hi = {}
    new_correct_option = None

    for new_label, old_key in zip(OPTION_KEYS, shuffled_keys):
        new_options_en[new_label] = mcq["options_en"][old_key]
        if mcq.get("options_hi"):
            new_options_hi[new_label] = mcq["options_hi"].get(old_key, "")
        # Track which new label carries the correct answer
        if old_key == original_correct_key:
            new_correct_option = new_label

    mcq["options_en"] = new_options_en
    if mcq.get("options_hi"):
        mcq["options_hi"] = new_options_hi
    mcq["correct_option"] = new_correct_option

    # Verification (never fail silently)
    assert mcq["options_en"][new_correct_option] == original_correct_value_en, (
        f"RESHUFFLE INTEGRITY FAILURE: correct answer value changed! "
        f"Expected '{original_correct_value_en}', got '{mcq['options_en'][new_correct_option]}'"
    )

    return mcq


# ─────────────────────────────────────────────────────────────
# TASK A3 — BATCH STRUCTURE CREATION
# ─────────────────────────────────────────────────────────────

def create_batches(mcqs_by_subject: dict[str, list]) -> dict[str, list[list]]:
    """
    Split each subject's MCQs into BATCHES_PER_SUBJECT groups of MCQS_PER_BATCH.
    Returns {subject: [[batch1_mcqs], [batch2_mcqs], ...]}
    """
    batches = {}
    for subject, mcqs in mcqs_by_subject.items():
        if len(mcqs) < TOTAL_PER_SUBJECT:
            print(f"  ⚠️  WARNING: {subject} has only {len(mcqs)} MCQs, expected {TOTAL_PER_SUBJECT}")
        
        subject_batches = []
        for i in range(BATCHES_PER_SUBJECT):
            start = i * MCQS_PER_BATCH
            end = start + MCQS_PER_BATCH
            batch = mcqs[start:end]
            if batch:
                subject_batches.append(batch)
        batches[subject] = subject_batches
    return batches


# ─────────────────────────────────────────────────────────────
# TASK A4 — DATABASE INGESTION
# ─────────────────────────────────────────────────────────────

def get_or_create_subject(db, name: str) -> Subject:
    subj = db.query(Subject).filter(Subject.name == name).first()
    if not subj:
        subj = Subject(name=name)
        db.add(subj)
        db.commit()
        db.refresh(subj)
    return subj


def get_or_create_topic(db, name: str, subject_id: int) -> Topic:
    topic = db.query(Topic).filter(Topic.name == name, Topic.subject_id == subject_id).first()
    if not topic:
        topic = Topic(name=name, subject_id=subject_id)
        db.add(topic)
        db.commit()
        db.refresh(topic)
    return topic


def ingest_batches(db, batches: dict[str, list[list]], dry_run: bool = False) -> dict:
    """Upload all batches into DB. Returns ingestion summary."""
    summary = {
        "subjects": {},
        "total_tests_created": 0,
        "total_questions_created": 0,
        "errors": []
    }

    for subject_name, subject_batches in batches.items():
        print(f"\n📚 Processing subject: {subject_name} ({len(subject_batches)} batches)")
        subj_obj = get_or_create_subject(db, subject_name) if not dry_run else None
        subj_summary = {"batches": [], "question_count": 0}

        for batch_idx, batch_mcqs in enumerate(subject_batches, start=1):
            batch_num = batch_idx
            test_title = f"{subject_name} Batch {batch_num}"

            # Check if test already exists — skip to avoid duplicates
            if not dry_run:
                existing = db.query(Test).filter(Test.title == test_title).first()
                if existing:
                    print(f"  ⏭️  Skipping (already exists): {test_title}")
                    continue

            if dry_run:
                print(f"  [DRY RUN] Would create: {test_title} with {len(batch_mcqs)} questions")
                subj_summary["batches"].append({"title": test_title, "q_count": len(batch_mcqs)})
                summary["total_questions_created"] += len(batch_mcqs)
                summary["total_tests_created"] += 1
                continue

            # Create Test
            test = Test(
                title=test_title,
                description=f"{subject_name} practice batch {batch_num} of {BATCHES_PER_SUBJECT}.",
                subject_id=subj_obj.id,
                duration_minutes=TEST_DURATION_MINUTES,
                correct_marks=CORRECT_MARKS,
                negative_marking_value=NEGATIVE_MARKING_VALUE,
                is_active=True
            )
            db.add(test)
            db.commit()
            db.refresh(test)

            # Create Questions
            q_count = 0
            for mcq in batch_mcqs:
                topic_name = mcq.get("topic", f"{subject_name} General")
                topic_obj = get_or_create_topic(db, topic_name, subj_obj.id)

                question = Question(
                    test_id=test.id,
                    topic_id=topic_obj.id,
                    text_en=mcq["text_en"],
                    text_hi=mcq.get("text_hi"),
                    options_en=mcq["options_en"],
                    options_hi=mcq.get("options_hi"),
                    correct_option=mcq["correct_option"],
                    explanation_en=mcq.get("explanation_en"),
                    explanation_hi=mcq.get("explanation_hi"),
                    difficulty=mcq.get("difficulty", "MEDIUM"),
                    source=mcq.get("source"),
                )
                db.add(question)
                q_count += 1

            db.commit()
            print(f"  ✅ Created: {test_title} ({q_count} questions)")
            subj_summary["batches"].append({"title": test_title, "q_count": q_count})
            subj_summary["question_count"] += q_count
            summary["total_tests_created"] += 1
            summary["total_questions_created"] += q_count

        summary["subjects"][subject_name] = subj_summary

    return summary


# ─────────────────────────────────────────────────────────────
# TASK A5 — ADMIN VERIFICATION REPORT
# ─────────────────────────────────────────────────────────────

def print_verification_report(db):
    """Print a post-ingestion verification table for admin confirmation."""
    print("\n" + "=" * 65)
    print("  ADMIN VERIFICATION REPORT — PRODUCTION CONTENT STATUS")
    print("=" * 65)
    print(f"  {'Subject':<15} {'Batches':>8} {'Questions':>10} {'Active':>8}")
    print("-" * 65)

    for subject_name in SUBJECTS:
        subj = db.query(Subject).filter(Subject.name == subject_name).first()
        if not subj:
            print(f"  {subject_name:<15} {'MISSING':>8}")
            continue

        tests = db.query(Test).filter(Test.subject_id == subj.id).all()
        total_q = sum(
            db.query(Question).filter(Question.test_id == t.id).count()
            for t in tests
        )
        active_count = sum(1 for t in tests if t.is_active)
        print(f"  {subject_name:<15} {len(tests):>8} {total_q:>10} {active_count:>8}")

    print("=" * 65)
    total_tests = db.query(Test).count()
    total_questions = db.query(Question).count()
    print(f"  {'TOTAL':<15} {total_tests:>8} {total_questions:>10}")
    print("=" * 65 + "\n")


# ─────────────────────────────────────────────────────────────
# MAIN PIPELINE
# ─────────────────────────────────────────────────────────────

def run_pipeline(data_file: str, dry_run: bool = False, reshuffle_seed: int = 42):
    print(f"\n{'='*65}")
    print(f"  MCQ PRODUCTION CONTENT PIPELINE")
    print(f"  Data file : {data_file}")
    print(f"  Dry run   : {dry_run}")
    print(f"  Seed      : {reshuffle_seed}")
    print(f"{'='*65}\n")

    # Load raw data
    with open(data_file, encoding="utf-8") as f:
        raw_mcqs = json.load(f)
    print(f"✅ Loaded {len(raw_mcqs)} raw MCQs from file")

    # ── A1: Normalize ──────────────────────────────────────────
    print("\n── TASK A1: Normalizing MCQs ──")
    normalized = []
    errors = []
    seen_texts = set()

    for idx, mcq in enumerate(raw_mcqs):
        mcq = normalize_mcq(mcq)
        validation_errors = validate_mcq(mcq, idx)
        if validation_errors:
            errors.extend(validation_errors)
            continue
        # Deduplicate by question text
        key = (mcq["subject"], mcq["text_en"].lower()[:80])
        if key in seen_texts:
            print(f"  ⚠️  Duplicate skipped at index {idx}")
            continue
        seen_texts.add(key)
        normalized.append(mcq)

    if errors:
        print(f"\n❌ Validation errors found ({len(errors)}):")
        for e in errors[:20]:
            print(f"   {e}")
        if len(errors) > 20:
            print(f"   ... and {len(errors) - 20} more")
    print(f"✅ {len(normalized)} valid MCQs after normalization ({len(errors)} invalid skipped)")

    # ── A2: Reshuffle ──────────────────────────────────────────
    print("\n── TASK A2: Reshuffling options (deterministic) ──")
    reshuffled = []
    for idx, mcq in enumerate(normalized):
        seed = reshuffle_seed + idx  # unique seed per question for determinism
        reshuffled.append(reshuffle_options(mcq, seed))
    print(f"✅ {len(reshuffled)} MCQs reshuffled with seed base {reshuffle_seed}")

    # ── A3: Group by subject & create batches ──────────────────
    print("\n── TASK A3: Creating batch structure ──")
    by_subject = defaultdict(list)
    for mcq in reshuffled:
        by_subject[mcq["subject"]].append(mcq)

    for subj in SUBJECTS:
        count = len(by_subject.get(subj, []))
        status = "✅" if count >= TOTAL_PER_SUBJECT else "⚠️ "
        print(f"  {status} {subj}: {count}/{TOTAL_PER_SUBJECT} MCQs")

    batches = create_batches(by_subject)

    # ── A4: Ingest into DB ────────────────────────────────────
    print(f"\n── TASK A4: Database ingestion (dry_run={dry_run}) ──")
    db = SessionLocal()
    try:
        summary = ingest_batches(db, batches, dry_run=dry_run)
    finally:
        if not dry_run:
            db.close()

    print(f"\n✅ Ingestion complete:")
    print(f"   Tests created   : {summary['total_tests_created']}")
    print(f"   Questions loaded: {summary['total_questions_created']}")

    # ── A5: Admin verification ────────────────────────────────
    if not dry_run:
        verify_db = SessionLocal()
        try:
            print_verification_report(verify_db)
        finally:
            verify_db.close()
    else:
        print("\n[DRY RUN] Skipping live verification report.")

    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MCQ Production Content Pipeline")
    parser.add_argument("--data-file", required=True, help="Path to JSON MCQ data file")
    parser.add_argument("--dry-run", action="store_true", help="Run without writing to DB")
    parser.add_argument("--reshuffle-seed", type=int, default=42, help="Base random seed for reshuffling")
    args = parser.parse_args()

    run_pipeline(
        data_file=args.data_file,
        dry_run=args.dry_run,
        reshuffle_seed=args.reshuffle_seed
    )
