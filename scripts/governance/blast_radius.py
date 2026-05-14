import json
import sys
from pathlib import Path

def calculate_blast_radius(target_file, graph_path):
    with open(graph_path, "r") as f:
        graph = json.load(f)

    impacted = {target_file}
    stack = [target_file]

    while stack:
        current = stack.pop()
        current_no_ext = str(Path(current).with_suffix("")).replace("\\", "/")
        
        for dep in graph["dependencies"]:
            target_parts = dep["target"].split(".")
            target_norm = "/".join(target_parts)
            if "app/" in target_norm:
                target_norm = "backend/" + target_norm
            
            # If the current file (or its base) is what the dependency targets
            if target_norm.startswith(current_no_ext) or current_no_ext.startswith(target_norm):
                if dep["source"] not in impacted:
                    impacted.add(dep["source"])
                    stack.append(dep["source"])

    return sorted(list(impacted))

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python blast_radius.py <file_path>")
        sys.exit(1)
    
    target = sys.argv[1].replace("\\", "/")
    impact = calculate_blast_radius(target, "docs/governance/ARCHITECTURE_GRAPH.json")
    
    print(f"Blast Radius for {target}:")
    for file in impact:
        print(f" - {file}")
