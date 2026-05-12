"""
Reshuffle Integrity Validator
==============================
Standalone validator to verify that option reshuffling NEVER breaks:
1. The semantic correctness of the correct answer
2. The question text
3. The scoring logic (correct_option label maps to the right value)

Usage:
    python scripts/validate_reshuffle.py --data-file data/mcqs.json --seed 42
"""

import os
import sys
import json
import argparse

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.production_content_pipeline import (
    normalize_mcq, reshuffle_options, validate_mcq, OPTION_KEYS
)


def validate_reshuffle_integrity(data_file: str, seed: int = 42):
    print(f"\n{'='*60}")
    print("  RESHUFFLE INTEGRITY VALIDATOR")
    print(f"{'='*60}\n")

    with open(data_file, encoding="utf-8") as f:
        raw_mcqs = json.load(f)

    passed = 0
    failed = 0
    failures = []

    for idx, mcq in enumerate(raw_mcqs):
        mcq = normalize_mcq(mcq)
        errs = validate_mcq(mcq, idx)
        if errs:
            continue  # Skip invalid MCQs — normalization pipeline handles them

        original_text = mcq["text_en"]
        original_correct_key = mcq["correct_option"]
        original_correct_value = mcq["options_en"][original_correct_key]

        try:
            reshuffled = reshuffle_options(mcq, seed + idx)
        except AssertionError as e:
            failed += 1
            failures.append(f"[{idx}] ASSERTION FAILED: {e}")
            continue

        # Check 1: Question text unchanged
        if reshuffled["text_en"] != original_text:
            failed += 1
            failures.append(f"[{idx}] QUESTION TEXT CHANGED!")
            continue

        # Check 2: Correct answer semantic value preserved
        new_correct_key = reshuffled["correct_option"]
        new_correct_value = reshuffled["options_en"][new_correct_key]
        if new_correct_value != original_correct_value:
            failed += 1
            failures.append(
                f"[{idx}] ANSWER VALUE CHANGED! "
                f"Before: '{original_correct_value}' After: '{new_correct_value}'"
            )
            continue

        # Check 3: All 4 options still present (no data loss)
        if set(reshuffled["options_en"].keys()) != set(OPTION_KEYS):
            failed += 1
            failures.append(f"[{idx}] OPTION KEYS MALFORMED: {reshuffled['options_en'].keys()}")
            continue

        # Check 4: Option VALUES set is unchanged (just reordered)
        if set(reshuffled["options_en"].values()) != set(mcq["options_en"].values()):
            failed += 1
            failures.append(f"[{idx}] OPTION VALUES SET CHANGED (data lost or added)!")
            continue

        passed += 1

    print(f"  Total validated : {passed + failed}")
    print(f"  ✅ Passed       : {passed}")
    print(f"  ❌ Failed       : {failed}")

    if failures:
        print(f"\n  FAILURES:")
        for f_msg in failures[:20]:
            print(f"    {f_msg}")

    print(f"\n{'='*60}")
    if failed == 0:
        print("  ✅ ALL RESHUFFLE INTEGRITY CHECKS PASSED")
        print("  Option reshuffling is safe for production deployment.")
    else:
        print("  ❌ INTEGRITY FAILURES DETECTED — DO NOT DEPLOY")
    print(f"{'='*60}\n")
    return failed == 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Validate MCQ reshuffle integrity")
    parser.add_argument("--data-file", required=True, help="Path to JSON MCQ data file")
    parser.add_argument("--seed", type=int, default=42, help="Base seed matching the pipeline")
    args = parser.parse_args()

    success = validate_reshuffle_integrity(args.data_file, args.seed)
    sys.exit(0 if success else 1)
