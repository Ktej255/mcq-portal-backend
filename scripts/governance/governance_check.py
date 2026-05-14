import sys
import subprocess
import os

def run_blast_radius(file_path):
    cmd = ["python", "backend/scripts/governance/blast_radius.py", file_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout

def check_governance(file_path):
    print(f"--- GOVERNANCE CHECK: {file_path} ---")
    
    # 1. Check if file is in a frozen layer
    frozen_files = [
        "backend/app/models/domain.py",
        "backend/app/services/scoring_engine.py",
        "backend/app/services/report_service.py"
    ]
    
    is_frozen = any(f in file_path for f in frozen_files)
    
    # 2. Calculate Blast Radius
    radius_output = run_blast_radius(file_path)
    impact_count = len(radius_output.split("\n")) - 2 # Subtract header and empty line
    
    print(f"Impact Score: {impact_count} files")
    
    if is_frozen:
        print("!!! CRITICAL: FILE IS IN FROZEN LAYER !!!")
        print("This file governs mathematical or data truth. Mutations are HIGHLY RESTRICTED.")
    
    if impact_count > 10:
        print("WARNING: HIGH BLAST RADIUS DETECTED.")
    
    print("\nImpacted Files:")
    print(radius_output)
    
    print("-----------------------------------------")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python governance_check.py <file_path>")
        sys.exit(1)
    
    check_governance(sys.argv[1])
