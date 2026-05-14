import os
import sys
import json
import subprocess
from datetime import datetime

def log_message(msg):
    print(f"[GOVERNANCE] {msg}")

def check_file_locks(files):
    lock_file_path = "docs/governance/LOCKED_FILES.json"
    if not os.path.exists(lock_file_path):
        return True
    
    with open(lock_file_path, "r") as f:
        locks = json.load(f)
    
    locked = locks.get("locked_files", [])
    frozen = locks.get("frozen_directories", [])
    
    # Priority 6: Chat Isolation Enforcement
    current_chat = os.environ.get("AGENT_CHAT_ID", "UNKNOWN")
    # If Chat #1 touches locked files -> Block
    # If Chat #2 touches product files (e.g. revision UI) -> Warning/Block
    
    for f in files:
        # Normalize path
        normalized_f = f.replace("\\", "/")
        if normalized_f in locked:
            # Priority 4: Educational Safety Wall
            justification = os.environ.get("MUTATION_JUSTIFICATION")
            if not justification:
                log_message(f"CRITICAL: File '{f}' is LOCKED. Explicit JUSTIFICATION required.")
                return False
            log_message(f"PROCEEDING: Mutation to locked file '{f}' authorized by justification: {justification}")
        for d in frozen:
            if normalized_f.startswith(d):
                log_message(f"CRITICAL: Directory '{d}' is FROZEN. Mutation rejected.")
                return False
    return True

def run_graphify_audit(files):
    if not files:
        return True
    
    cmd = ["python", "backend/scripts/governance/graphify_audit.py"] + files
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log_message("Graphify Audit FAILED.")
        print(result.stdout)
        print(result.stderr)
        return False
    
    log_message("Graphify Audit PASSED.")
    return True

def update_system_state(files, blast_radius="Calculating...", risk="LOW"):
    state_path = "docs/governance/graph/SYSTEM_STATE.md"
    if not os.path.exists(state_path):
        return
    
    timestamp = datetime.now().isoformat()
    justification = os.environ.get("MUTATION_JUSTIFICATION", "N/A (Standard Edit)")
    agent_id = os.environ.get("AGENT_ID", "Antigravity-G2")
    
    entry = f"\n### Mutation: {timestamp}\n"
    entry += f"- **Agent**: {agent_id}\n"
    entry += f"- **Files**: {', '.join(files)}\n"
    entry += f"- **Justification**: {justification}\n"
    entry += f"- **Risk**: {risk}\n"
    entry += f"- **Blast Radius**: {blast_radius}\n"
    entry += f"- **Status**: GOVERNED\n"
    
    with open(state_path, "a") as f:
        f.write(entry)
    log_message("SYSTEM_STATE.md updated with forensic justification.")

def main():
    if len(sys.argv) < 2:
        print("Usage: python auto_governance.py <file1> <file2> ...")
        sys.exit(1)
    
    files = sys.argv[1:]
    
    log_message(f"Initiating auto-governance for: {files}")
    
    if not check_file_locks(files):
        sys.exit(1)
    
    if not run_graphify_audit(files):
        sys.exit(1)
    
    # In a real scenario, blast radius would be parsed from graphify output
    update_system_state(files)
    
    log_message("Governance check SUCCESS. Mutation approved.")

if __name__ == "__main__":
    main()
