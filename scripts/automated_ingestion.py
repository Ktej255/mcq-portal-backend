import os
import re
import json
import random
import unicodedata
from typing import List, Dict, Any, Optional
from PyPDF2 import PdfReader
from docx import Document
import sys

# Add parent dir to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import SessionLocal
from app.models.domain import Subject, Topic, Test, Question

class MCQParser:
    """AG-2: Flexible MCQ Parser for multiple formats."""
    
    @staticmethod
    def extract_text_from_pdf(path: str) -> str:
        try:
            reader = PdfReader(path)
            text = ""
            for page in reader.pages:
                text += page.extract_text() + "\n"
            return text
        except Exception as e:
            print(f"Error reading PDF {path}: {e}")
            return ""

    @staticmethod
    def extract_text_from_docx(path: str) -> str:
        try:
            doc = Document(path)
            return "\n".join([p.text for p in doc.paragraphs])
        except Exception as e:
            print(f"Error reading DOCX {path}: {e}")
            return ""

    @staticmethod
    def parse_mcqs(text: str) -> List[Dict[str, Any]]:
        """Parse MCQs with elite-grade tolerance and adaptive strategy."""
        text = unicodedata.normalize("NFC", text)
        
        # 1. Identify Answer Key (Flexible Token-based)
        ans_key = {}
        # Pattern: Q, then digits, then anything until (option)
        # Handle cases like "51 (b)" or "51. (b)" or "**Q51** (b)"
        # Also handles "Q101: (a)"
        tokens = re.findall(r'(?i)(?:Q|Que)?(\d+)\s*[^A-Da-d0-9\(\)\[\]]*\s*[\(\[]?([A-Da-d])[\)\]]', text)
        for q_num, opt in tokens:
            if q_num not in ans_key:
                ans_key[q_num] = opt.upper()
        
        # 2. Split into Question Blocks (Aggressive)
        # Matches Q1. or 1. or (1) at start of lines or after substantial whitespace
        q_pattern = re.compile(r'(?m)(?:^\s*|\s{4,})(?:\*\*|__)?\s*(?:Q|Que|Question)?\.?\s*(\d+)\s*[\.:\)\-]', re.IGNORECASE)
        
        blocks = []
        matches = list(q_pattern.finditer(text))
        for i in range(len(matches)):
            start = matches[i].start()
            next_start = matches[i+1].start() if i + 1 < len(matches) else len(text)
            
            blocks.append((matches[i].group(1), text[start:next_start]))
            
        parsed_mcqs = []
        for q_num, block in blocks:
            mcq = MCQParser._parse_block(block)
            if mcq:
                # If no answer in block, check if q_num is in ans_key
                # Also handle case where q_num in block is e.g. "1" but ans_key has "101" (if it's a batch starting at 101)
                # We'll try to match the last few digits or just the number
                q_key = str(q_num)
                if not mcq.get("correct_option") and q_key in ans_key:
                    mcq["correct_option"] = ans_key[q_key]
                
                if mcq.get("correct_option"):
                    parsed_mcqs.append(mcq)
        
        return parsed_mcqs

    @staticmethod
    def _parse_block(block: str) -> Optional[Dict[str, Any]]:
        """Extract components with high tolerance and clean boundary detection."""
        lines = [line.strip() for line in block.split('\n') if line.strip()]
        if not lines: return None
            
        def has_hindi(text):
            return any('\u0900' <= char <= '\u097f' for char in text)

        def split_bilingual(text):
            if has_hindi(text):
                match = re.search(r'[\u0900-\u097f]', text)
                if match and match.start() > 5:
                    return text[:match.start()].strip(), text[match.start():].strip()
                return "", text.strip()
            return text.strip(), ""

        # Extract Question Text
        question_match = re.search(r'(?:Q|Que|Question)?\.?\s*\d+\s*[\.:\)\-]\s*(.*)', lines[0], re.IGNORECASE)
        raw_question = question_match.group(1) if question_match else lines[0]
        
        options_en, options_hi = {}, {}
        option_map = {'A': 'A', 'B': 'B', 'C': 'C', 'D': 'D', 'a': 'A', 'b': 'B', 'c': 'C', 'd': 'D'}
        
        opt_pattern = re.compile(r'^\s*[\(\[]?([a-dA-D])[\)\]\.\-\s]', re.IGNORECASE)
        ans_pattern = re.compile(r'(?i)(?:Ans|Answer|Correct|Correct Answer)[:\.\-]?\s*[\(\[]?([A-Da-d])', re.IGNORECASE)
        
        # Identify indices
        options_start_idx = -1
        ans_idx = -1
        correct_option = None
        
        for i, line in enumerate(lines):
            if options_start_idx == -1 and opt_pattern.match(line):
                options_start_idx = i
            ans_match = ans_pattern.search(line)
            if ans_match and ans_idx == -1:
                ans_idx = i
                correct_option = option_map[ans_match.group(1)]

        # Question text refinement
        q_limit = options_start_idx if options_start_idx > 0 else (ans_idx if ans_idx > 0 else len(lines))
        if q_limit > 1:
            raw_question = " ".join([raw_question] + lines[1:q_limit])
        q_en, q_hi = split_bilingual(raw_question)

        # Options extraction with proper boundaries
        if options_start_idx != -1:
            current_key = None
            limit = ans_idx if ans_idx != -1 else len(lines)
            for i in range(options_start_idx, limit):
                line = lines[i]
                opt_match = opt_pattern.match(line)
                if opt_match:
                    current_key = option_map[opt_match.group(1)]
                    val_en, val_hi = split_bilingual(line[opt_match.end():].strip())
                    options_en[current_key] = val_en or val_hi
                    if val_hi: options_hi[current_key] = val_hi
                elif current_key:
                    # STOP capturing if it looks like a NEW question or an Answer tag
                    if re.match(r'^\s*(?:Q|Que|Question)?\.?\s*\d+\s*[\.:\)\-]', line, re.IGNORECASE) or ans_pattern.search(line):
                        break
                    v_en, v_hi = split_bilingual(line)
                    options_en[current_key] += " " + (v_en or v_hi)
                    if v_hi: options_hi[current_key] = (options_hi.get(current_key, "") + " " + v_hi).strip()

        # Explanation
        raw_exp = ""
        if ans_idx != -1:
            ans_line = lines[ans_idx]
            match = ans_pattern.search(ans_line)
            suffix = ans_line[match.end():].strip()
            raw_exp = " ".join([suffix] + lines[ans_idx+1:])
            
        exp_en, exp_hi = split_bilingual(raw_exp)

        if not options_en or len(options_en) < 2: return None
            
        return {
            "text_en": q_en or q_hi,
            "text_hi": q_hi if q_en else None,
            "options_en": options_en,
            "options_hi": options_hi if options_hi else None,
            "correct_option": correct_option,
            "explanation_en": exp_en or exp_hi,
            "explanation_hi": exp_hi if exp_en else None
        }

class AutomatedContentIngestor:
    """AG-1, AG-3, AG-4, AG-5: Automated Directory Scanner and Ingestor."""
    
    def __init__(self, root_dir: str):
        self.root_dir = root_dir
        self.subjects = ["Environment", "Polity", "History", "Science", "Economy", "Geography"]
        self.report = {
            "total_parsed": 0,
            "total_ingested": 0,
            "failed": [],
            "subjects": {},
            "duplicates": 0
        }
        self.db = SessionLocal()
        self.seen_questions = set()

    def scan_and_ingest(self):
        print(f"Scanning directory: {self.root_dir}")
        
        # Mapping for S&T
        subject_folder_map = {
            "Environment": "Environment",
            "Polity": "Polity",
            "History": "History",
            "Science": "S & T",
            "Economy": "Economy",
            "Geography": "Geography"
        }
        
        for subject in self.subjects:
            print(f"Processing subject: {subject}")
            self.report["subjects"][subject] = {"parsed": 0, "ingested": 0, "batches": 0}
            
            folder_name = subject_folder_map.get(subject, subject)
            subject_path = os.path.join(self.root_dir, folder_name)
            
            # Step A: Pre-create 8 Batches (AG-3)
            # This ensures they are visible in UI even if empty ("Coming Soon")
            subj_db = self.db.query(Subject).filter(Subject.name == subject).first()
            if not subj_db:
                subj_db = Subject(name=subject)
                self.db.add(subj_db)
                self.db.commit()
                self.db.refresh(subj_db)
            
            for i in range(1, 9):
                title = f"{subject} Batch {i}"
                test = self.db.query(Test).filter(Test.title == title, Test.subject_id == subj_db.id).first()
                if not test:
                    test = Test(
                        title=title,
                        description=f"Most Probable MCQs for {subject} - Batch {i}",
                        subject_id=subj_db.id,
                        duration_minutes=60,
                        is_active=True
                    )
                    self.db.add(test)
            self.db.commit()

            # Step B: Scan for content
            all_subject_mcqs = []
            if os.path.exists(subject_path):
                all_subject_mcqs = self._process_subject_dir(subject, subject_path)
            
            # Step C: Ingest content into the pre-created batches
            if all_subject_mcqs:
                self._ingest_subject_mcqs(subject, all_subject_mcqs)
            
        self._save_report()
        self.db.close()

    def _process_subject_dir(self, subject: str, path: str) -> List[Dict[str, Any]]:
        all_mcqs = []
        q_files = []
        a_files = []
        
        print(f"  Walking directory: {path}")
        for root, dirs, files in os.walk(path):
            for file in files:
                file_path = os.path.join(root, file)
                file_lower = file.lower()
                
                # STRICT RULE: Only process files with "Batch" in the name
                if "batch" not in file_lower:
                    continue

                if "ans" in file_lower or "key" in file_lower:
                    a_files.append(file_path)
                else:
                    q_files.append(file_path)

        # 2. Bimodal Ingestion (Join Q-files and A-files)
        for qf in q_files:
            match = re.search(r'batch[\s_]*(\d+)', os.path.basename(qf), re.IGNORECASE)
            if match:
                batch_num = int(match.group(1))
                # Look for matching answer file
                af = next((f for f in a_files if re.search(rf'batch[\s_]*0?{batch_num}', os.path.basename(f), re.IGNORECASE)), None)
                
                print(f"    Processing Batch {batch_num}: {os.path.basename(qf)}")
                q_text = self._read_file_content(qf)
                parsed = []
                if af:
                    a_text = self._read_file_content(af)
                    if q_text and a_text:
                        combined = q_text + "\n\n=== ANSWER KEY ===\n\n" + a_text
                        parsed = MCQParser.parse_mcqs(combined)
                else:
                    if q_text:
                        parsed = MCQParser.parse_mcqs(q_text)
                
                if parsed:
                    for m in parsed:
                        m["batch_id"] = batch_num
                    print(f"      Parsed {len(parsed)} MCQs")
                    all_mcqs.extend(parsed)

        return all_mcqs

    def _read_file_content(self, file_path: str) -> str:
        ext = os.path.splitext(file_path)[1].lower()
        try:
            if ext == ".pdf":
                return MCQParser.extract_text_from_pdf(file_path)
            elif ext == ".docx":
                return MCQParser.extract_text_from_docx(file_path)
            elif ext in [".txt", ".md", ".json"]:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    return f.read()
        except Exception as e:
            print(f"    Error reading {os.path.basename(file_path)}: {e}")
        return ""

    def _ingest_subject_mcqs(self, subject_name: str, mcqs: List[Dict[str, Any]]):
        # A3: Auto-batch creation (50 per batch, max 8 batches)
        valid_mcqs = []
        for mcq in mcqs:
            # A4: Safe Reshuffling
            processed = self._reshuffle_and_validate(mcq)
            if processed:
                # Deduplicate
                q_key = processed["text_en"].strip().lower()
                if q_key not in self.seen_questions:
                    self.seen_questions.add(q_key)
                    valid_mcqs.append(processed)
                else:
                    self.report["duplicates"] += 1
            else:
                self.report["failed"].append({"mcq": mcq["text_en"][:50] if "text_en" in mcq else "Unknown", "reason": "Reshuffle validation failed"})

        # Get Subject ID
        subj = self.db.query(Subject).filter(Subject.name == subject_name).first()
        if not subj:
            subj = Subject(name=subject_name)
            self.db.add(subj)
            self.db.commit()
            self.db.refresh(subj)

        # Create batches
        batch_size = 50
        num_batches = min(8, (len(valid_mcqs) + batch_size - 1) // batch_size)
        
        for i in range(num_batches):
            batch_mcqs = valid_mcqs[i*batch_size : (i+1)*batch_size]
            if not batch_mcqs: continue
            
            test_title = f"{subject_name} Batch {i+1}"
            test = self.db.query(Test).filter(Test.title == test_title).first()
            if not test:
                test = Test(
                    title=test_title,
                    description=f"Automated practice batch for {subject_name}",
                    subject_id=subj.id,
                    duration_minutes=60,
                    correct_marks=2.0,
                    negative_marking_value=0.66,
                    is_active=True
                )
                self.db.add(test)
                self.db.commit()
                self.db.refresh(test)
            
            for m in batch_mcqs:
                # Topic mapping (placeholder or simple mapping)
                topic = self.db.query(Topic).filter(Topic.name == f"{subject_name} Core", Topic.subject_id == subj.id).first()
                if not topic:
                    topic = Topic(name=f"{subject_name} Core", subject_id=subj.id)
                    self.db.add(topic)
                    self.db.commit()
                    self.db.refresh(topic)
                
                question = Question(
                    test_id=test.id,
                    topic_id=topic.id,
                    text_en=m["text_en"],
                    text_hi=m.get("text_hi"),
                    options_en=m["options_en"],
                    options_hi=m.get("options_hi"),
                    correct_option=m["correct_option"],
                    explanation_en=m.get("explanation_en"),
                    explanation_hi=m.get("explanation_hi")
                )
                self.db.add(question)
            
            self.db.commit()
            self.report["subjects"][subject_name]["ingested"] += len(batch_mcqs)
            self.report["subjects"][subject_name]["batches"] += 1
            self.report["total_ingested"] += len(batch_mcqs)

    def _reshuffle_and_validate(self, mcq: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """AG-4: Safe Option Reshuffling with validation (Bilingual)."""
        try:
            original_correct_text_en = mcq["options_en"][mcq["correct_option"]].strip()
            
            # Reshuffle
            keys = list(mcq["options_en"].keys())
            random.shuffle(keys)
            
            new_options_en = {}
            new_options_hi = {}
            new_correct_option = None
            
            for i, old_key in enumerate(keys):
                new_key = chr(65 + i) # A, B, C, D
                new_options_en[new_key] = mcq["options_en"][old_key]
                if mcq.get("options_hi") and old_key in mcq["options_hi"]:
                    new_options_hi[new_key] = mcq["options_hi"][old_key]
                
                if old_key == mcq["correct_option"]:
                    new_correct_option = new_key
            
            # Validation
            if new_options_en[new_correct_option].strip() != original_correct_text_en:
                return None
                
            mcq["options_en"] = new_options_en
            if new_options_hi: mcq["options_hi"] = new_options_hi
            mcq["correct_option"] = new_correct_option
            return mcq
        except Exception:
            return None

    def _save_report(self):
        with open("production_ingestion_report.json", "w") as f:
            json.dump(self.report, f, indent=4)
        print("Ingestion complete. Report saved to production_ingestion_report.json")

if __name__ == "__main__":
    path = r"D:\Graphology\Paid Students\Mians ready Dec 2025\Morning Batch\30 day Plan"
    ingestor = AutomatedContentIngestor(path)
    ingestor.scan_and_ingest()
