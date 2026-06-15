import pytest
from app.services.mcq_variation_engine import (
    get_stable_seed,
    parse_statement_subset,
    build_subset_text_en,
    MCQVariationEngine
)

def test_stable_seed():
    seed1 = get_stable_seed(123, 456)
    seed2 = get_stable_seed(123, 456)
    seed3 = get_stable_seed(123, 457)
    
    assert seed1 == seed2
    assert seed1 != seed3
    assert isinstance(seed1, int)

def test_parse_statement_subset():
    assert parse_statement_subset("1 and 2 only") == {1, 2}
    assert parse_statement_subset("2 and 3 only") == {2, 3}
    assert parse_statement_subset("1 only") == {1}
    assert parse_statement_subset("Neither 1 nor 2") == set()
    assert parse_statement_subset("None of the above") == set()

def test_build_subset_text_en():
    assert build_subset_text_en({1}) == "1 only"
    assert build_subset_text_en({1, 2}) == "1 and 2 only"
    assert build_subset_text_en({1, 2, 3}) == "1, 2 and 3"

def test_option_shuffling_dict():
    text_en = "What is the capital of India?"
    options_en = {
        "A": "New Delhi",
        "B": "Mumbai",
        "C": "Kolkata",
        "D": "Chennai"
    }
    correct_option = "A"
    
    # Run mutation
    mutated = MCQVariationEngine.mutate_question(
        question_id=1,
        attempt_id=10,
        text_en=text_en,
        text_hi=None,
        options_en=options_en,
        options_hi=None,
        correct_option=correct_option
    )
    
    # Assert keys are preserved
    assert set(mutated["options_en"].keys()) == {"A", "B", "C", "D"}
    
    # Assert values are shuffled (or same, but keys map back)
    key_mapping = mutated["key_mapping"]
    new_corr = mutated["correct_option"]
    
    # Mapping back new_corr should yield original correct_option
    assert key_mapping[new_corr] == correct_option
    
    # Presenter value at new_corr should be "New Delhi"
    assert mutated["options_en"][new_corr] == "New Delhi"

def test_query_inversion_subsets():
    text_en = "Consider the following statements: \n1. Statement 1\n2. Statement 2\n3. Statement 3\nWhich of the statements given above are correct?"
    options_en = {
        "A": "1 and 2 only",
        "B": "2 and 3 only",
        "C": "1 and 3 only",
        "D": "1, 2 and 3"
    }
    correct_option = "A" # 1 and 2 only
    
    # Seed attempt & question to trigger query inversion (needs random < 0.5)
    # Let's find seed that triggers inversion
    attempt_id = 1
    inverted = False
    for q_id in range(100):
        mutated = MCQVariationEngine.mutate_question(
            question_id=q_id,
            attempt_id=attempt_id,
            text_en=text_en,
            text_hi=None,
            options_en=options_en,
            options_hi=None,
            correct_option=correct_option,
            statements_en=["1", "2", "3"]
        )
        if "incorrect" in mutated["text_en"]:
            inverted = True
            # Assert mathematical inversion of option subsets:
            # "1 and 2 only" -> complement {1, 2, 3} - {1, 2} = {3} -> "3 only"
            # "2 and 3 only" -> complement {1} -> "1 only"
            # "1 and 3 only" -> complement {2} -> "2 only"
            # "1, 2 and 3" -> complement {} -> "None of the above" or "Neither 1 nor 2"
            
            key_mapping = mutated["key_mapping"]
            new_corr = mutated["correct_option"]
            
            # Map back new correct option to original option
            orig_opt = key_mapping[new_corr]
            assert orig_opt == "A"
            
            # Shuffled correct option should hold the complement of "1 and 2 only" which is "3 only"
            assert mutated["options_en"][new_corr] == "3 only"
            break
            
    assert inverted, "Failed to find a seed that triggers query inversion"

def test_query_inversion_how_many():
    text_en = "Consider the following statements: \n1. Statement 1\n2. Statement 2\n3. Statement 3\nHow many of the statements given above are correct?"
    options_en = {
        "A": "Only one",
        "B": "Only two",
        "C": "All three",
        "D": "None"
    }
    correct_option = "B" # "Only two"
    
    # Search for an inverting seed
    inverted = False
    for q_id in range(100):
        mutated = MCQVariationEngine.mutate_question(
            question_id=q_id,
            attempt_id=1,
            text_en=text_en,
            text_hi=None,
            options_en=options_en,
            options_hi=None,
            correct_option=correct_option,
            statements_en=["1", "2", "3"]
        )
        if "incorrect" in mutated["text_en"]:
            inverted = True
            # N=3. Original correct count is 2 ("Only two").
            # Inverted correct count is 3 - 2 = 1.
            # So the new correct option should be "Only one" (which was key "A" in original options).
            
            new_corr = mutated["correct_option"]
            key_mapping = mutated["key_mapping"]
            
            # Shuffled correct option maps back to A (original "Only one" option)
            assert key_mapping[new_corr] == "A"
            assert mutated["options_en"][new_corr] == "Only one"
            break
            
    assert inverted, "Failed to find a seed that triggers query inversion for how many"
