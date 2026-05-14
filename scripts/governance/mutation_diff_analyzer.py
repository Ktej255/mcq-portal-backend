import sys
import os
import re

def analyze_diff(diff_content):
    issues = []
    
    # Pattern 1: Huge deletions + reinsertions (sign of full file rewrite)
    deletions = len(re.findall(r"^-", diff_content, re.MULTILINE))
    insertions = len(re.findall(r"^\+", diff_content, re.MULTILINE))
    
    if deletions > 100 and insertions > 100:
        # Check if the ratio is close (indicates a likely full rewrite)
        if 0.8 < (deletions / insertions) < 1.2:
            issues.append("CRITICAL: Potential full-file rewrite detected (AI confusion coding). Use patches instead.")

    # Pattern 2: Formatting only rewrites (churn)
    # If many lines changed but net lines is near 0 and content is similar
    if deletions == insertions and deletions > 50:
        issues.append("WARNING: High-churn diff detected. Potential formatting or style rewrite without logic changes.")

    # Pattern 3: Duplicated logic keywords
    logic_keywords = ["calculate_score", "generate_report", "submit_attempt"]
    for kw in logic_keywords:
        if diff_content.count(kw) > 4: # Arbitrary threshold for duplication in a single diff
            issues.append(f"WARNING: Multiple instances of '{kw}' logic detected in diff. Check for duplication.")

    # Pattern 4: Massive JSX replacement
    if "<" in diff_content and ">" in diff_content:
        if insertions > 200:
            issues.append("CRITICAL: Massive JSX regeneration detected. High risk of UI regression.")

    return issues

def main():
    if sys.stdin.isatty():
        print("Usage: git diff | python mutation_diff_analyzer.py")
        return

    diff_content = sys.stdin.read()
    if not diff_content:
        return

    issues = analyze_diff(diff_content)
    
    if issues:
        print("\n" + "!"*50)
        print("      INSTITUTIONAL MUTATION AUDIT WARNING")
        print("!"*50)
        for issue in issues:
            print(f"- {issue}")
        print("!"*50)
        sys.exit(1)
    else:
        print("[AUDIT] Mutation diff clean. Logic integrity maintained.")

if __name__ == "__main__":
    main()
