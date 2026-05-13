import random
import time
from typing import List, Dict, Any

class StudentPersona:
    def __init__(self, name: str, behaviors: Dict[str, Any]):
        self.name = name
        self.behaviors = behaviors # e.g. pacing, accuracy, hesitation_prob

def simulate_attempt(persona: StudentPersona, questions: List[Dict[str, Any]]):
    """
    Simulates a student attempt based on persona behaviors.
    """
    print(f"--- Simulating Persona: {persona.name} ---")
    results = []
    events = []
    
    start_time = time.time()
    
    for i, q in enumerate(questions):
        # 1. Pacing (Time spent)
        pacing = persona.behaviors.get("pacing", 30)
        actual_time = max(5, random.gauss(pacing, pacing * 0.2))
        
        # 2. Hesitation (Behavioral Signal)
        if random.random() < persona.behaviors.get("hesitation_prob", 0.1):
            events.append({"type": "HESITATION", "question_id": q["id"], "duration": actual_time * 0.5})
            
        # 3. Accuracy (Outcome)
        is_correct = random.random() < persona.behaviors.get("accuracy", 0.5)
        
        # 4. Option Revision
        if random.random() < persona.behaviors.get("revision_prob", 0.05):
            events.append({"type": "OPTION_REVISION", "question_id": q["id"], "from": "A", "to": "B"})

        results.append({
            "question_id": q["id"],
            "selected_option": q["correct_option"] if is_correct else random.choice(["A", "B", "C", "D"]),
            "is_correct": is_correct,
            "time_spent": actual_time
        })
        
        events.append({"type": "QUESTION_VIEW", "question_id": q["id"]})
        events.append({"type": "OPTION_SELECT", "question_id": q["id"]})

    print(f"Simulation Complete: {len(results)} questions answered.")
    return {"results": results, "events": events}

# Personas
PERSONAS = {
    "Perfect": StudentPersona("Perfect", {"accuracy": 1.0, "pacing": 45, "hesitation_prob": 0.01}),
    "Panic": StudentPersona("Panic", {"accuracy": 0.3, "pacing": 10, "hesitation_prob": 0.4, "revision_prob": 0.3}),
    "Mobile_Distracted": StudentPersona("Mobile", {"accuracy": 0.5, "pacing": 60, "hesitation_prob": 0.5}),
    "Partial": StudentPersona("Partial", {"accuracy": 0.8, "pacing": 30, "skip_prob": 0.5})
}
