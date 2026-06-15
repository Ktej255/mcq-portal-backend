import hashlib
import random
import re
from typing import Any, Dict, List, Tuple, Union

CANONICAL_OPTION_KEYS = ["A", "B", "C", "D", "E", "F"]

def get_stable_seed(attempt_id: int, question_id: int) -> int:
    """Generates a stable, platform-independent integer seed."""
    key = f"{attempt_id}_{question_id}".encode("utf-8")
    return int(hashlib.sha256(key).hexdigest(), 16) & 0xffffffff

# --- Core String Replacements for Inversion ---
EN_INVERSION_PATTERNS = [
    (r"\b(is/are|are)\s+correct\b", "are incorrect"),
    (r"\b(is/are|are)\s+not\s+correct\b", "are correct"),
    (r"\b(is/are|are)\s+incorrect\b", "are correct"),
    (r"\b(is/are|are)\s+not\s+incorrect\b", "are incorrect"),
]

HI_INVERSION_PATTERNS = [
    (r"सही\s+हैं?\b", "गलत हैं"),
    (r"सही\s+नहीं\s+हैं?\b", "सही हैं"),
    (r"गलत\s+हैं?\b", "सही हैं"),
]

# --- Subset mapping parser ---
# Extract numbers from string like "1 and 2 only" -> {1, 2}
def parse_statement_subset(text: str) -> set:
    if not text:
        return set()
    text_lower = text.lower()
    if "neither" in text_lower or "none" in text_lower or "कोई भी नहीं" in text_lower:
        return set()
    numbers = set()
    for m in re.finditer(r"\b(\d+)\b", text):
        numbers.add(int(m.group(1)))
    return numbers

def build_subset_text_en(subset: set) -> str:
    if not subset:
        return "Neither 1 nor 2" if random.choice([True, False]) else "None of the above"
    sorted_sub = sorted(list(subset))
    if len(sorted_sub) == 1:
        return f"{sorted_sub[0]} only"
    elif len(sorted_sub) == 2:
        return f"{sorted_sub[0]} and {sorted_sub[1]} only"
    else:
        comma_part = ", ".join(str(n) for n in sorted_sub[:-1])
        return f"{comma_part} and {sorted_sub[-1]}"

def build_subset_text_hi(subset: set) -> str:
    if not subset:
        return "कोई भी नहीं"
    sorted_sub = sorted(list(subset))
    if len(sorted_sub) == 1:
        return f"केवल {sorted_sub[0]}"
    elif len(sorted_sub) == 2:
        return f"केवल {sorted_sub[0]} और {sorted_sub[1]}"
    else:
        comma_part = ", ".join(str(n) for n in sorted_sub[:-1])
        return f"केवल {comma_part} और {sorted_sub[-1]}"

def try_invert_options(
    options_list: List[Dict[str, Any]], N: int
) -> Tuple[List[Dict[str, Any]], bool]:
    """
    Attempts to mathematically invert statement combination options.
    Returns the inverted options list and a boolean indicating success.
    """
    inverted = []
    for opt in options_list:
        text_en = opt.get("textEn") or opt.get("text_en") or opt.get("text") or ""
        text_hi = opt.get("textHi") or opt.get("text_hi") or ""
        
        subset = parse_statement_subset(text_en)
        if not subset and "neither" not in text_en.lower() and "none" not in text_en.lower() and "1" not in text_en:
            # Not a statement combination question or parsing failed
            return options_list, False
            
        comp = set(range(1, N + 1)) - subset
        new_text_en = build_subset_text_en(comp)
        new_text_hi = build_subset_text_hi(comp)
        
        new_opt = dict(opt)
        # Preserve original keys/structure
        if "textEn" in new_opt: new_opt["textEn"] = new_text_en
        if "text_en" in new_opt: new_opt["text_en"] = new_text_en
        if "text" in new_opt: new_opt["text"] = new_text_en
        
        if "textHi" in new_opt: new_opt["textHi"] = new_text_hi
        if "text_hi" in new_opt: new_opt["text_hi"] = new_text_hi
        
        inverted.append(new_opt)
    return inverted, True

def try_invert_how_many(
    options_list: List[Dict[str, Any]], correct_option: str, N: int
) -> Tuple[List[Dict[str, Any]], str, bool]:
    """
    Inverts 'How many of the statements given above are correct?' style questions.
    Returns (inverted_options, new_correct_option, success)
    """
    # Find matching count for correct_option
    correct_idx = -1
    for i, opt in enumerate(options_list):
        opt_id = opt.get("id", "")
        # opt_id can be like 'q_opt_A' or just 'A'
        if opt_id.endswith(f"_{correct_option}") or opt_id == correct_option:
            correct_idx = i
            break
            
    if correct_idx == -1:
        return options_list, correct_option, False
        
    # Standard count maps:
    # Index 0: "Only one" / "One" -> 1
    # Index 1: "Only two" / "Two" -> 2
    # Index 2: "All three" / "Three" -> 3 (or "All four" if N=4)
    # Index 3: "None" -> 0
    # Let's map standard indexes:
    # If N = 3:
    # 1 -> maps to 3 - 1 = 2 (Index 1)
    # 2 -> maps to 3 - 2 = 1 (Index 0)
    # 3 -> maps to 3 - 3 = 0 (Index 3)
    # 0 -> maps to 3 - 0 = 3 (Index 2)
    
    # Let's extract counts from option texts
    counts = []
    for opt in options_list:
        text = (opt.get("textEn") or opt.get("text") or "").lower()
        if "one" in text or "एक" in text:
            counts.append(1)
        elif "two" in text or "दो" in text:
            counts.append(2)
        elif "three" in text or "तीन" in text:
            counts.append(3)
        elif "four" in text or "चार" in text:
            counts.append(4)
        elif "none" in text or "कोई" in text or "neither" in text:
            counts.append(0)
        else:
            counts.append(-1)
            
    if any(c == -1 for c in counts):
        return options_list, correct_option, False
        
    orig_count = counts[correct_idx]
    new_count = N - orig_count
    
    # Find index of new_count
    try:
        new_idx = counts.index(new_count)
    except ValueError:
        return options_list, correct_option, False
        
    new_correct_opt_id = options_list[new_idx].get("id", "")
    new_correct_option = new_correct_opt_id.rsplit("_opt_", 1)[-1] if "_opt_" in new_correct_opt_id else new_correct_opt_id
    
    return options_list, new_correct_option, True


# --- Main Variation Engine ---

class MCQVariationEngine:
    @staticmethod
    def mutate_question(
        question_id: int,
        attempt_id: int,
        text_en: str,
        text_hi: str | None,
        options_en: Any,
        options_hi: Any | None,
        correct_option: str,
        explanation_en: str | None = None,
        explanation_hi: str | None = None,
        statements_en: List[str] | None = None,
    ) -> Dict[str, Any]:
        """
        Mutates a question dynamically and deterministically.
        Returns a dictionary containing the mutated question details.
        """
        seed = get_stable_seed(attempt_id, question_id)
        rng = random.Random(seed)
        
        mutated_text_en = text_en
        mutated_text_hi = text_hi or ""
        mutated_correct_option = correct_option
        mutated_explanation_en = explanation_en or ""
        mutated_explanation_hi = explanation_hi or ""
        
        # Determine number of statements N
        N = len(statements_en) if statements_en else 0
        if N == 0:
            # Try to infer N from numbering in text
            numbered = re.findall(r"\b(\d+)\.\s", text_en)
            if numbered:
                try:
                    N = max(int(num) for num in numbered)
                except ValueError:
                    N = 0

        # Standardise option lists
        raw_options = []
        is_dict = isinstance(options_en, dict)
        
        if is_dict:
            for key in sorted(options_en.keys()):
                text_hi_val = options_hi.get(key) if isinstance(options_hi, dict) else ""
                raw_options.append({
                    "id": key,
                    "textEn": options_en[key],
                    "textHi": text_hi_val
                })
        elif isinstance(options_en, list):
            for idx, opt_item in enumerate(options_en):
                opt_hi_val = ""
                if isinstance(options_hi, list) and idx < len(options_hi):
                    opt_hi_val = options_hi[idx].get("text") if isinstance(options_hi[idx], dict) else options_hi[idx]
                elif isinstance(options_hi, dict):
                    opt_hi_val = options_hi.get(str(idx)) or options_hi.get(CANONICAL_OPTION_KEYS[idx]) or ""
                
                if isinstance(opt_item, dict):
                    raw_options.append({
                        "id": opt_item.get("id", str(idx)),
                        "textEn": opt_item.get("text", opt_item.get("text_en", opt_item.get("textEn", ""))),
                        "textHi": opt_hi_val
                    })
                else:
                    raw_options.append({
                        "id": CANONICAL_OPTION_KEYS[idx] if idx < len(CANONICAL_OPTION_KEYS) else str(idx),
                        "textEn": opt_item,
                        "textHi": opt_hi_val
                    })
        else:
            # If options are unstructured, fallback to no-op
            return {
                "text_en": text_en,
                "text_hi": text_hi,
                "options_en": options_en,
                "options_hi": options_hi,
                "correct_option": correct_option,
                "explanation_en": explanation_en,
                "explanation_hi": explanation_hi,
                "key_mapping": {k: k for k in CANONICAL_OPTION_KEYS}
            }

        # --- 1. Query Inversion (50% chance if query inversion patterns match) ---
        has_inversion_match = False
        for pattern, _ in EN_INVERSION_PATTERNS:
            if re.search(pattern, text_en, re.IGNORECASE):
                has_inversion_match = True
                break
                
        inverted_successfully = False
        if has_inversion_match and N >= 2 and rng.random() < 0.5:
            # Determine if it's "how many" or standard subset combinations
            is_how_many = "how many" in text_en.lower() or (text_hi is not None and "कितने" in text_hi)
            
            if is_how_many:
                new_opts, new_correct, ok = try_invert_how_many(raw_options, correct_option, N)
                if ok:
                    raw_options = new_opts
                    mutated_correct_option = new_correct
                    inverted_successfully = True
            else:
                new_opts, ok = try_invert_options(raw_options, N)
                if ok:
                    raw_options = new_opts
                    # Correct option key remains same in subset complement mapping
                    inverted_successfully = True
            
            if inverted_successfully:
                # Perform the string inversion in English & Hindi question text
                for pattern, replacement in EN_INVERSION_PATTERNS:
                    mutated_text_en, count = re.subn(pattern, replacement, mutated_text_en, flags=re.IGNORECASE)
                    if count > 0:
                        break
                if text_hi:
                    for pattern, replacement in HI_INVERSION_PATTERNS:
                        mutated_text_hi, count = re.subn(pattern, replacement, mutated_text_hi)
                        if count > 0:
                            break
                            
                note_en = f"\n\n[Note: This question was dynamically inverted from the original master question to ask for INCORRECT statements.]"
                note_hi = f"\n\n[नोट: इस प्रश्न को मूल प्रश्न से गतिशील रूप से बदलकर 'गलत' कथनों के बारे में पूछा गया है।]"
                mutated_explanation_en += note_en
                if mutated_explanation_hi:
                    mutated_explanation_hi += note_hi

        # --- 2. Option Shuffling ---
        # Extract the original IDs from raw_options
        orig_ids = [opt["id"] for opt in raw_options]
        
        # Shuffle the values but assign them to keys A, B, C, D in order
        shuffled_values = list(raw_options)
        rng.shuffle(shuffled_values)
        
        # Presenter keys are standard CANONICAL_OPTION_KEYS
        pres_keys = CANONICAL_OPTION_KEYS[:len(raw_options)]
        
        mutated_options_list = []
        key_mapping = {} # maps presenter_key -> original_key
        
        for p_key, orig_val in zip(pres_keys, shuffled_values):
            orig_key = orig_val["id"]
            key_mapping[p_key] = orig_key
            
            mutated_options_list.append({
                "id": p_key,
                "textEn": orig_val["textEn"],
                "textHi": orig_val["textHi"]
            })
            
            if orig_key == mutated_correct_option:
                mutated_correct_option = p_key

        # Re-package options to match original format
        if is_dict:
            final_options_en = {opt["id"]: opt["textEn"] for opt in mutated_options_list}
            final_options_hi = {opt["id"]: opt["textHi"] for opt in mutated_options_list}
        else:
            # List structure
            final_options_en = [{"id": opt["id"], "text": opt["textEn"]} for opt in mutated_options_list]
            final_options_hi = [{"id": opt["id"], "text": opt["textHi"]} for opt in mutated_options_list]

        return {
            "text_en": mutated_text_en,
            "text_hi": mutated_text_hi if text_hi else None,
            "options_en": final_options_en,
            "options_hi": final_options_hi if text_hi else None,
            "correct_option": mutated_correct_option,
            "explanation_en": mutated_explanation_en if explanation_en else None,
            "explanation_hi": mutated_explanation_hi if explanation_hi else None,
            "key_mapping": key_mapping
        }
