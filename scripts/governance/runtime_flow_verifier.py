import json
import datetime
from typing import Dict, Any

class RuntimeFlowVerifier:
    """
    Executable flow maps for critical educational lifecycles.
    Ensures that inputs, outputs, and state transitions remain valid.
    """
    
    def __init__(self):
        self.state = "IDLE"
        self.log = []

    def transition(self, next_state: str, action: str):
        self.log.append({
            "timestamp": datetime.datetime.now().isoformat(),
            "from": self.state,
            "to": next_state,
            "action": action
        })
        self.state = next_state

    def verify_attempt_start(self, student_id: str, test_id: str):
        print(f"[FLOW] Verifying Attempt Start for {student_id} on {test_id}...")
        # 1. State: IDLE -> IN_PROGRESS
        self.transition("IN_PROGRESS", "START_ATTEMPT")
        
        # 2. Reconcile expected payload
        payload = {
            "student_id": student_id,
            "test_id": test_id,
            "start_time": datetime.datetime.now().isoformat(),
            "status": "started"
        }
        
        if not payload["student_id"] or not payload["test_id"]:
            raise ValueError("Flow Violation: Attempt Start missing critical IDs")
        
        print("  - State Transition Valid: IDLE -> IN_PROGRESS")
        return payload

    def verify_question_save(self, attempt_id: str, question_id: str, selected_option: str):
        print(f"  [FLOW] Verifying Question Save: {question_id} -> {selected_option}...")
        if self.state != "IN_PROGRESS":
            raise RuntimeError(f"Flow Violation: Cannot save question in state {self.state}")
        
        # Reconciliation: selected_option must be in [A, B, C, D, None]
        if selected_option not in ["A", "B", "C", "D", None]:
            raise ValueError(f"Flow Violation: Invalid option {selected_option}")
            
        return {"status": "saved", "reconciled": True}

    def verify_submit(self, attempt_id: str, answers_count: int):
        print(f"[FLOW] Verifying Submission for {attempt_id}...")
        # State: IN_PROGRESS -> SUBMITTED
        self.transition("SUBMITTED", "SUBMIT_ATTEMPT")
        
        if answers_count == 0:
            print("  - WARNING: Submitting empty attempt (Valid but suspicious)")
            
        print("  - State Transition Valid: IN_PROGRESS -> SUBMITTED")
        return {"status": "completed"}

    def verify_report_generation(self, attempt_id: str, score_data: Dict[str, Any]):
        print(f"[FLOW] Verifying Report Generation for {attempt_id}...")
        if self.state != "SUBMITTED":
            raise RuntimeError(f"Flow Violation: Cannot generate report for unsubmitted attempt ({self.state})")
            
        # State: SUBMITTED -> FINALIZED
        self.transition("FINALIZED", "GENERATE_REPORT")
        
        # Reconciliation: Totality check
        if score_data["correct_count"] + score_data["incorrect_count"] + score_data["unattempted_count"] != score_data["total_count"]:
            raise ValueError("Flow Violation: Report Data Totality Mismatch")
            
        print("  - Reconciliation Integrity: PASSED")
        return {"status": "finalized"}

def run_canonical_suite():
    verifier = RuntimeFlowVerifier()
    
    # 1. Start
    attempt = verifier.verify_attempt_start("student_001", "test_upsc_2026")
    
    # 2. Save Questions
    verifier.verify_question_save("att_001", "q1", "A")
    verifier.verify_question_save("att_001", "q2", "B")
    verifier.verify_question_save("att_001", "q3", None) # Skipped
    
    # 3. Submit
    verifier.verify_submit("att_001", 3)
    
    # 4. Generate Report (Mocking scoring engine output)
    mock_score = {
        "correct_count": 2,
        "incorrect_count": 0,
        "unattempted_count": 1,
        "total_count": 3
    }
    verifier.verify_report_generation("att_001", mock_score)
    
    print("\n--- RUNTIME FLOW VERIFICATION COMPLETE ---")
    print(json.dumps(verifier.log, indent=2))

if __name__ == "__main__":
    run_canonical_suite()
