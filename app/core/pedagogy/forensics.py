import hashlib
import json
from typing import Dict, Any
from .contracts import MCQStructure, IngestionFingerprint

class MCQForensics:
    @staticmethod
    def generate_fingerprint(mcq: MCQStructure) -> IngestionFingerprint:
        # Normalize text for hashing (strip whitespace, consistent casing for structural elements)
        normalized_text = mcq.text_en.strip()
        
        # 1. Content Hash (Question text and metadata)
        content_payload = {
            "text": normalized_text,
            "subject": mcq.subject,
            "topic": mcq.topic,
            "difficulty": mcq.difficulty
        }
        content_hash = hashlib.sha256(json.dumps(content_payload, sort_keys=True).encode()).hexdigest()
        
        # 2. Structure Hash (Statements and Type)
        structure_payload = {
            "type": mcq.question_type.value,
            "statements": [s.strip() for s in mcq.statements_en]
        }
        structure_hash = hashlib.sha256(json.dumps(structure_payload, sort_keys=True).encode()).hexdigest()
        
        # 3. Options Hash (Text and Correct Answer)
        options_payload = {
            "options": [{"id": o.id, "text": o.text_en} for o in mcq.options],
            "correct_option": mcq.correct_option
        }
        options_hash = hashlib.sha256(json.dumps(options_payload, sort_keys=True).encode()).hexdigest()
        
        # 4. Global Integrity Hash
        global_payload = {
            "content": content_hash,
            "structure": structure_hash,
            "options": options_hash
        }
        integrity_hash = hashlib.sha256(json.dumps(global_payload, sort_keys=True).encode()).hexdigest()
        
        return IngestionFingerprint(
            content_hash=content_hash,
            structure_hash=structure_hash,
            options_hash=options_hash,
            integrity_hash=integrity_hash
        )

    @staticmethod
    def verify_integrity(mcq: MCQStructure, fingerprint: IngestionFingerprint) -> bool:
        new_fp = MCQForensics.generate_fingerprint(mcq)
        return new_fp.integrity_hash == fingerprint.integrity_hash
