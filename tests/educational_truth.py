import unittest
from typing import List, Any
from dataclasses import dataclass
from enum import Enum

# Mock domain objects for testing without DB
class ConfidenceLevel(Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    UNKNOWN = "UNKNOWN"

@dataclass
class Topic:
    name: str
    subject: Any = None

@dataclass
class Question:
    id: int
    correct_option: str
    topic: Topic = None

@dataclass
class Answer:
    question_id: int
    selected_option: str
    is_skipped: bool = False
    time_taken_seconds: int = 0
    confidence_level: ConfidenceLevel = ConfidenceLevel.UNKNOWN

@dataclass
class Test:
    correct_marks: float = 2.0
    negative_marking_value: float = 0.66

# The Actual Logic (Imported or Re-implemented for isolation)
from backend.app.services.scoring_engine import ScoringEngine

class TestEducationalTruth(unittest.TestCase):
    def setUp(self):
        self.topic1 = Topic(name="Fundamental Rights")
        self.questions = [
            Question(id=1, correct_option="A", topic=self.topic1),
            Question(id=2, correct_option="B", topic=self.topic1),
            Question(id=3, correct_option="C", topic=self.topic1),
            Question(id=4, correct_option="D", topic=self.topic1),
            Question(id=5, correct_option="A", topic=self.topic1),
        ]
        self.test_config = Test(correct_marks=2.0, negative_marking_value=0.66)

    def test_invariants_balanced_attempt(self):
        """
        Scenario: 2 Correct, 1 Incorrect, 2 Skipped.
        Total: 5
        """
        answers = [
            Answer(question_id=1, selected_option="A", confidence_level=ConfidenceLevel.HIGH), # Correct
            Answer(question_id=2, selected_option="B", confidence_level=ConfidenceLevel.MEDIUM), # Correct
            Answer(question_id=3, selected_option="A", confidence_level=ConfidenceLevel.LOW), # Incorrect (Correct is C)
            Answer(question_id=4, selected_option=None, is_skipped=True), # Skipped
            Answer(question_id=5, selected_option=None, is_skipped=True), # Skipped
        ]
        
        result = ScoringEngine.calculate_score(self.test_config, self.questions, answers)
        
        # INVARIANT 1: Totality
        self.assertEqual(result["correct_count"] + result["incorrect_count"] + result["unattempted_count"], result["total_count"], "Totality Invariant Failed")
        self.assertEqual(result["total_count"], 5)
        self.assertEqual(result["correct_count"], 2)
        self.assertEqual(result["incorrect_count"], 1)
        self.assertEqual(result["unattempted_count"], 2)
        
        # INVARIANT 2: Scoring Formula
        expected_score = (2 * 2.0) - (1 * 0.66)
        self.assertAlmostEqual(result["total_score"], expected_score, places=2, msg="Scoring Formula Invariant Failed")
        
        # INVARIANT 3: Accuracy vs Mastery
        # Accuracy = 2 / 3 = 66.66%
        # Mastery = 2 / 5 = 40.0%
        self.assertAlmostEqual(result["accuracy"], 66.66, places=1)
        self.assertAlmostEqual(result["mastery_percentage"], 40.0, places=1)

    def test_zero_attempt_safety(self):
        """
        Scenario: All skipped.
        """
        answers = [Answer(question_id=i, selected_option=None, is_skipped=True) for i in range(1, 6)]
        result = ScoringEngine.calculate_score(self.test_config, self.questions, answers)
        
        self.assertEqual(result["attempted_count"], 0)
        self.assertEqual(result["accuracy"], 0.0)
        self.assertEqual(result["total_score"], 0.0)

    def test_perfect_score(self):
        """
        Scenario: All correct.
        """
        answers = [Answer(question_id=q.id, selected_option=q.correct_option) for q in self.questions]
        result = ScoringEngine.calculate_score(self.test_config, self.questions, answers)
        
        self.assertEqual(result["correct_count"], 5)
        self.assertEqual(result["total_score"], 10.0)
        self.assertEqual(result["accuracy"], 100.0)
        self.assertEqual(result["mastery_percentage"], 100.0)

if __name__ == "__main__":
    unittest.main()
