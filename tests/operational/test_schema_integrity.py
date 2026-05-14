import unittest
import json
import os
from app.schemas.test_engine import ReportResponse

class TestSchemaIntegrity(unittest.TestCase):
    """
    PROTECTION SUITE: Ensures API schemas remain backwards-compatible.
    Protects against silent deletions of fields that the frontend expects.
    """
    
    def setUp(self):
        self.baseline_report_path = os.path.join("backend", "tests", "data", "baseline_report.json")
        with open(self.baseline_report_path, "r") as f:
            self.baseline_report = json.load(f)
            
        self.baseline_start_path = os.path.join("backend", "tests", "data", "baseline_start_attempt.json")
        with open(self.baseline_start_path, "r") as f:
            self.baseline_start = json.load(f)

    def test_report_response_backwards_compatibility(self):
        # Ensure the current Pydantic model can still parse the baseline data
        try:
            report = ReportResponse(**self.baseline_report)
            self.assertEqual(report.attempt_id, 123)
        except Exception as e:
            self.fail(f"Schema Integrity Violation: ReportResponse cannot parse baseline! Error: {e}")

    def test_start_attempt_response_backwards_compatibility(self):
        from app.schemas.test_engine import StartAttemptResponse
        try:
            start = StartAttemptResponse(**self.baseline_start)
            self.assertEqual(start.attempt_id, 456)
            self.assertEqual(start.test.duration_minutes, 60)
        except Exception as e:
            self.fail(f"Schema Integrity Violation: StartAttemptResponse cannot parse baseline! Error: {e}")

    def test_mandatory_fields_presence(self):
        # Explicitly check for fields the frontend Dashboard/Report pages rely on
        mandatory_fields = [
            "attempt_id", "total_score", "accuracy", "correct_count", 
            "incorrect_count", "unattempted_count", "topic_wise_analysis",
            "generated_at"
        ]
        model_fields = ReportResponse.model_fields
        for field in mandatory_fields:
            self.assertIn(field, model_fields, f"CRITICAL: Field '{field}' removed from ReportResponse! Frontend will BREAK.")

if __name__ == "__main__":
    unittest.main()
