import json
import sys
import os

GRAPH_PATH = "docs/governance/graph/graph.json"

def load_graph():
    with open(GRAPH_PATH, 'r') as f:
        return json.load(f)

def get_impact(target_file, graph_data):
    target_id = None
    target_file_norm = target_file.replace("\\", "/")
    
    for node in graph_data['nodes']:
        if 'source_file' in node:
            node_file = node['source_file'].replace("\\", "/")
            if node_file == target_file_norm or node_file.endswith(target_file_norm):
                target_id = node['id']
                break
    
    if not target_id:
        return None

    # Reverse edges to find who depends on us
    dependents = []
    for item in graph_data['nodes']:
        if 'source' in item and 'target' in item:
            if item['target'] == target_id:
                dependents.append(item['source'])

    node_map = {n['id']: n for n in graph_data['nodes'] if 'id' in n}
    dependent_files = []
    for d_id in dependents:
        node = node_map.get(d_id)
        if node and 'source_file' in node:
            dependent_files.append(node['source_file'])
    
    return dependent_files

def main():
    if len(sys.argv) < 2:
        print("Usage: python impact_explorer.py <file>")
        sys.exit(1)

    file_query = sys.argv[1]
    graph_data = load_graph()
    
    impact = get_impact(file_query, graph_data)
    
    if impact is None:
        print(f"Error: File '{file_query}' not found in graph.")
    else:
        print(f"\n--- IMPACT EXPLORER: {file_query} ---")
        print(f"Directly Impacted Files ({len(impact)}):")
        for f in sorted(impact):
            print(f"  - {f}")
        
        if not impact:
            print("  (None - This file is a terminal leaf or isolated)")

if __name__ == "__main__":
    main()
