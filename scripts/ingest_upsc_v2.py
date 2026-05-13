import os
import re
import json
import unicodedata
from typing import List, Dict, Any, Optional
from PyPDF2 import PdfReader
import sys

# Add parent dir to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import SessionLocal
from app.models.domain import Subject, Topic, Test, Question

class RobustUPSCParser:
    """AG-6: Rebuilt UPSC Parser for high-fidelity multi-statement MCQs."""
    
    @staticmethod
    def clean_text(text: str) -> str:
        text = unicodedata.normalize("NFC", text)
        # Fix common scientific notation/unicode issues if they got split
        # This is a bit risky but needed given the fragmented PDF output
        lines = text.split('\n')
        cleaned_lines = []
        for line in lines:
            line = line.strip()
            if not line: continue
            cleaned_lines.append(line)
        
        # Join lines that don't end in punctuation or structural markers
        result = []
        if cleaned_lines:
            current = cleaned_lines[0]
            for i in range(1, len(cleaned_lines)):
                prev = cleaned_lines[i-1]
                curr = cleaned_lines[i]
                
                # REVISED JOIN LOGIC (V3 - Protection for Options):
                # 1. If prev is JUST a marker, join it with its content
                # 2. If curr is a NEW structural element (Q1. or (a)), DO NOT join
                # 3. If prev doesn't end in a terminator, join ONLY IF curr isn't structural
                is_marker = re.match(r'^(?:[1-9]\.|[\(\[]?[a-d][\)\]\.])\s*$', prev, re.I)
                ends_with_terminator = re.search(r'[.?!:]\s*$', prev)
                is_structural_curr = re.match(r'^(?:Q\d+\.|[\(\[]?[a-d][\)\]\.])', curr, re.I)
                
                if (is_marker or not ends_with_terminator) and not is_structural_curr:
                    current += " " + curr
                else:
                    result.append(current)
                    current = curr
            result.append(current)
        
        return "\n".join(result)

    @staticmethod
    def extract_blocks(text: str) -> List[Dict[str, Any]]:
        # Identify question starts
        q_pattern = re.compile(r'(?m)^Q(\d+)\.')
        matches = list(q_pattern.finditer(text))
        
        blocks = []
        for i in range(len(matches)):
            q_num = matches[i].group(1)
            start = matches[i].start()
            end = matches[matches.index(matches[i])+1].start() if i + 1 < len(matches) else len(text)
            blocks.append({"num": q_num, "text": text[start:end]})
        return blocks

    @staticmethod
    def parse_question_block(block: str) -> Optional[Dict[str, Any]]:
        # PRE-PROCESS: Aggressively split clumped lines (e.g. 1. xxx 2. yyy or (a) xxx (b) yyy)
        # Handle statements 1. to 9.
        block = re.sub(r'(\s)([1-9]\.)', r'\n\2', block)
        # Handle options (a) to (d)
        block = re.sub(r'(\s)([\(\[]?[a-d][\)\]\.])', r'\n\2', block)
        
        lines = [l.strip() for l in block.split('\n') if l.strip()]
        if not lines: return None

        stem_parts = []
        statements = []
        select_instruction = ""
        options = {}
        
        state = "STEM"
        
        for line in lines:
            # Transitions
            if re.match(r'^[1-9]\.', line):
                state = "STATEMENTS"
            elif re.match(r'^(?:Which|Select|How many|Correct)', line, re.I):
                state = "SELECT"
            elif re.match(r'^[\(\[]?[a-d][\)\]\.]', line, re.I):
                state = "OPTIONS"
            
            if state == "STEM":
                if line.startswith('Q'):
                    line = re.sub(r'^Q\d+\.\s*', '', line)
                if line: stem_parts.append(line)
            elif state == "STATEMENTS":
                statements.append(line)
            elif state == "SELECT":
                select_instruction += " " + line
            elif state == "OPTIONS":
                match = re.match(r'^[\(\[]?([a-d])[\)\]\.](.*)', line, re.I)
                if match:
                    opt_key = match.group(1).upper()
                    opt_val = match.group(2).strip()
                    options[opt_key] = opt_val
                elif options:
                    last_key = list(options.keys())[-1]
                    options[last_key] += " " + line

        full_question = " ".join(stem_parts).strip()
        if statements:
            # FORCE NEWLINES for UPSC structure
            full_question += "\n\n" + "\n\n".join(statements)
        if select_instruction:
            full_question += "\n\n" + select_instruction.strip()

        return {
            "text": full_question,
            "options": options
        }

    @staticmethod
    def parse_answer_key(text: str) -> Dict[str, str]:
        ans_map = {}
        # Pattern for the table: 1 (a) or Q1: (a)
        table_matches = re.findall(r'(?:Q|●\s*Q)?(\d+)\s*[:→\->\s]*[\(\[]?([a-d])[\)\]]', text, re.I)
        for q, a in table_matches:
            ans_map[q] = a.upper()
            
        return ans_map

    @staticmethod
    def parse_explanations(text: str) -> Dict[str, str]:
        exp_map = {}
        # Pattern: (Q|● Q)151 -> (a): [explanation] until next bullet or Q
        # We handle both bullet and non-bullet starts
        pattern = re.compile(r'(?:^|[\n●])\s*Q?(\d+)\s*[→\->\s]*[\(\[]?[a-d][\)\]]:?\s*(.*?)(?=\n\s*(?:●\s*)?Q?\d+\s*[→\->\s]*[\(\[]?[a-d][\)\]]|$)', re.S | re.I)
        for match in pattern.finditer(text):
            q_num = match.group(1)
            content = match.group(2).strip()
            exp_map[q_num] = content
        return exp_map

def run_ingestion():
    db = SessionLocal()
    
    base_path = r"D:\Graphology\Paid Students\Mians ready Dec 2025\Morning Batch\30 day Plan\Environment\Most Probabale MCQ"
    
    batches = [
        {"q": "Batch 01 1 to 50 question.pdf", "a": "Ans Batch 1 (1 to 50).pdf", "num": 1},
        {"q": "Batch 2 (51 to 100).pdf", "a": "Ans Batch 2 (51 to 100).pdf", "num": 2},
        {"q": "Batch_3__101_to_150_.pdf", "a": "Batch_3__101_to_150_.pdf", "num": 3},
        {"q": "Batch 4 (151 to 200).pdf", "a": "Ans Batch 4 (151 to 200).pdf", "num": 4},
        {"q": "Batch_5__201_to_250_.pdf", "a": "Batch_5__201_to_250_.pdf", "num": 5},
        {"q": "Batch_6__251_to_300_.pdf", "a": "Batch_6__251_to_300_.pdf", "num": 6},
        {"q": "Batch_7__301_to_350_.pdf", "a": "Batch_7__301_to_350_.pdf", "num": 7},
        {"q": "Batch_8__351_to_400_.pdf", "a": "Batch_8__351_to_400_.pdf", "num": 8}
    ]
    
    for batch in batches:
        q_path = os.path.join(base_path, batch["q"])
        a_path = os.path.join(base_path, batch["a"])
        batch_num = batch["num"]
        
        print(f"\n--- PROCESSING BATCH {batch_num} ---")
        
        # 1. Extract Text
        print("Extracting Question Text...")
        q_reader = PdfReader(q_path)
        q_raw = "\n".join([p.extract_text() for p in q_reader.pages])
        q_clean = RobustUPSCParser.clean_text(q_raw)
        
        print("Extracting Answer Text...")
        a_reader = PdfReader(a_path)
        a_raw = "\n".join([p.extract_text() for p in a_reader.pages])
        a_clean = RobustUPSCParser.clean_text(a_raw)
        
        # 2. Parse components
        print("Parsing blocks...")
        q_blocks = RobustUPSCParser.extract_blocks(q_clean)
        ans_key = RobustUPSCParser.parse_answer_key(a_clean) 
        exp_map = RobustUPSCParser.parse_explanations(a_clean)
        
        print(f"Found {len(q_blocks)} question blocks.")
        print(f"Found {len(ans_key)} answers.")
        print(f"Found {len(exp_map)} explanations.")

        # Verification: Show Q1 parsed for first batch
        if batch_num == 1 and q_blocks:
            v_parsed = RobustUPSCParser.parse_question_block(q_blocks[0]["text"])
            print("\n" + "="*50)
            print("VERIFICATION: Q1 PARSED TEXT")
            print("-" * 50)
            print(v_parsed["text"])
            print("="*50 + "\n")
        
        # 3. Process into DB format
        subject_name = "Environment"
        
        subj = db.query(Subject).filter(Subject.name == subject_name).first()
        if not subj:
            subj = Subject(name=subject_name)
            db.add(subj)
            db.commit()
            db.refresh(subj)
        
        topic = db.query(Topic).filter(Topic.name == f"{subject_name} Core", Topic.subject_id == subj.id).first()
        if not topic:
            topic = Topic(name=f"{subject_name} Core", subject_id=subj.id)
            db.add(topic)
            db.commit()
            db.refresh(topic)

        test_title = f"{subject_name} Batch {batch_num}"
        test = db.query(Test).filter(Test.title == test_title).first()
        if not test:
            test = Test(
                title=test_title,
                description=f"Verified UPSC High-Fidelity Batch for {subject_name}",
                subject_id=subj.id,
                duration_minutes=60, 
                correct_marks=2.0,
                negative_marking_value=0.66,
                is_active=True
            )
            db.add(test)
            db.commit()
            db.refresh(test)
        
        # --- HARD CLEAN FOR THIS TEST ---
        from sqlalchemy import text
        # Delete related records
        res = db.execute(text("DELETE FROM cognitive_snapshots WHERE attempt_id IN (SELECT id FROM attempts WHERE test_id = :tid)"), {"tid": test.id})
        db.execute(text("DELETE FROM reports WHERE attempt_id IN (SELECT id FROM attempts WHERE test_id = :tid)"), {"tid": test.id})
        db.execute(text("DELETE FROM exam_events WHERE attempt_id IN (SELECT id FROM attempts WHERE test_id = :tid)"), {"tid": test.id})
        db.execute(text("DELETE FROM attempt_answers WHERE attempt_id IN (SELECT id FROM attempts WHERE test_id = :tid)"), {"tid": test.id})
        db.execute(text("DELETE FROM attempts WHERE test_id = :tid"), {"tid": test.id})
        q_del = db.execute(text("DELETE FROM questions WHERE test_id = :tid"), {"tid": test.id})
        db.commit()
        print(f"  Cleaned existing data. Deleted {q_del.rowcount} stale questions.")

        ingested_count = 0
        for block in q_blocks:
            q_num = block["num"]
            parsed = RobustUPSCParser.parse_question_block(block["text"])
            
            if not parsed or not parsed["options"]:
                print(f"WARNING: Could not parse options for Q{q_num}. Skipping.")
                continue
                
            correct_opt = ans_key.get(q_num)
            if not correct_opt:
                print(f"WARNING: No answer found for Q{q_num}. Skipping.")
                continue
                
            explanation = exp_map.get(q_num, "")
            
            # Validation: Check if it's a multi-statement question but we lost them
            if "Consider the following statements" in parsed["text"] and "\n1." not in parsed["text"]:
                print(f"CRITICAL: Statement loss detected in Q{q_num}. skipping.")
                continue

            question = Question(
                test_id=test.id,
                topic_id=topic.id,
                text_en=f"Q{q_num}. {parsed['text']}",
                options_en=parsed["options"],
                correct_option=correct_opt,
                explanation_en=explanation,
                source="UPSC Portal Verified",
                question_number=int(q_num)
            )
            db.add(question)
            ingested_count += 1

        # Update timer: 1.2 min per question (50 Qs = 60 mins)
        test.duration_minutes = max(60, int(ingested_count * 1.2))
        db.commit()
        print(f"  Successfully ingested {ingested_count} high-fidelity questions into {test_title}.")

    db.close()
    print("\nINGESTION TASK COMPLETE.")

if __name__ == "__main__":
    run_ingestion()
