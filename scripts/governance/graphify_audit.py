import json
import sys
import os
import datetime
import subprocess
from collections import deque

GRAPH_PATH = "docs/governance/graph/graph.json"
REGISTRY_DIR = "docs/governance/graph/mutations"
MAX_BLAST_RADIUS = 20
MAX_PATCH_FILES = 10

def load_graph():
    if not os.path.exists(GRAPH_PATH):
        print(f"Error: Graph file not found at {GRAPH_PATH}")
        sys.exit(1)
    with open(GRAPH_PATH, 'r') as f:
        return json.load(f)

def run_runtime_truth_tests():
    print("[INTEGRATION] Running Educational Truth Invariant Suite...")
    env = os.environ.copy()
    env["PYTHONPATH"] = "."
    res = subprocess.run([sys.executable, "backend/tests/educational_truth.py"], env=env, capture_output=True, text=True)
    if res.returncode != 0:
        print(res.stderr)
        return False, "Educational Truth Tests FAILED."
    
    print("[INTEGRATION] Running Runtime Flow Verifier...")
    res = subprocess.run([sys.executable, "backend/scripts/governance/runtime_flow_verifier.py"], env=env, capture_output=True, text=True)
    if res.returncode != 0:
        print(res.stderr)
        return False, "Runtime Flow Verification FAILED."
    
    return True, "All runtime checks PASSED."

def get_blast_radius(target_file, graph_data):
    target_id = None
    target_file_norm = target_file.replace("\\", "/")
    
    for node in graph_data['nodes']:
        if 'source_file' in node:
            node_file = node['source_file'].replace("\\", "/")
            if node_file == target_file_norm or node_file.endswith(target_file_norm):
                target_id = node['id']
                break
    
    if not target_id:
        return []

    adj = {}
    for item in graph_data['nodes']:
        if 'source' in item and 'target' in item:
            u, v = item['source'], item['target']
            if v not in adj: adj[v] = []
            adj[v].append(u)

    impacted = set()
    queue = deque([target_id])
    while queue:
        curr = queue.popleft()
        if curr in impacted: continue
        impacted.add(curr)
        for neighbor in adj.get(curr, []):
            if neighbor not in impacted:
                queue.append(neighbor)

    impacted_files = set()
    node_map = {n['id']: n for n in graph_data['nodes'] if 'id' in n}
    for node_id in impacted:
        node = node_map.get(node_id)
        if node and 'source_file' in node:
            impacted_files.add(node['source_file'].replace("\\", "/"))
    
    return sorted(list(impacted_files))

def check_governance(files_to_edit, graph_data):
    results = {
        "timestamp": datetime.datetime.now().isoformat(),
        "files_to_edit": files_to_edit,
        "violations": [],
        "impact_map": {},
        "risk_level": "LOW",
        "total_blast_radius": 0,
        "runtime_status": "PENDING"
    }
    
    l0_files = ["backend/app/models/domain.py", "backend/app/db/session.py"]
    all_impacted = set()

    if len(files_to_edit) > MAX_PATCH_FILES:
        results["violations"].append(f"PATCH SIZE VIOLATION: Batch too large ({len(files_to_edit)} files). Max {MAX_PATCH_FILES}.")

    for f in files_to_edit:
        f_norm = f.replace("\\", "/")
        if f_norm in l0_files:
            results["violations"].append(f"BOUNDARY VIOLATION: Attempting to mutate L0 CORE file: {f_norm}")
            
        radius = get_blast_radius(f, graph_data)
        all_impacted.update(radius)
        results["impact_map"][f] = {"count": len(radius)}

    results["total_blast_radius"] = len(all_impacted)
    if len(all_impacted) > MAX_BLAST_RADIUS:
        results["violations"].append(f"SYSTEMIC RISK: Total blast radius ({len(all_impacted)}) exceeds threshold.")

    # RUNTIME INTEGRATION
    success, msg = run_runtime_truth_tests()
    results["runtime_status"] = msg
    if not success:
        results["violations"].append(msg)

    return results

def main():
    if len(sys.argv) < 2:
        print("Usage: python graphify_audit.py <file1> <file2> ...")
        sys.exit(1)

    files = sys.argv[1:]
    graph_data = load_graph()
    
    print(f"--- GRAPHIFY + RUNTIME GOVERNANCE AUDIT ---")
    results = check_governance(files, graph_data)
    
    os.makedirs(REGISTRY_DIR, exist_ok=True)
    reg_file = os.path.join(REGISTRY_DIR, f"audit_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(reg_file, 'w') as f:
        json.dump(results, f, indent=2)

    print(f"Blast Radius: {results['total_blast_radius']}")
    print(f"Runtime Status: {results['runtime_status']}")

    if results["violations"]:
        print("\n!!! GOVERNANCE BLOCK !!!")
        for v in results["violations"]:
            print(f"- {v}")
        sys.exit(1)
    else:
        print("\n[PASSED] Full Systemic Audit Completed.")
        sys.exit(0)

if __name__ == "__main__":
    main()
