import json
import os

GRAPH_PATH = "docs/governance/graph/graph.json"
OUTPUT_PATH = "docs/governance/graph/SERVICE_MAP.md"

def load_graph():
    with open(GRAPH_PATH, 'r') as f:
        return json.load(f)

def generate_service_map(graph_data):
    services = {}
    
    # 1. Group nodes by service (directory)
    for node in graph_data['nodes']:
        if 'source_file' in node:
            f = node['source_file'].replace("\\", "/")
            parts = f.split('/')
            if len(parts) > 1:
                service = "/".join(parts[:2]) # e.g., backend/app or frontend/src
            else:
                service = "root"
            
            if service not in services:
                services[service] = {"files": set(), "dependencies": set(), "dependents": set()}
            services[service]["files"].add(f)

    # 2. Map dependencies between services
    adj = {}
    for item in graph_data['nodes']:
        if 'source' in item and 'target' in item:
            u, v = item['source'], item['target']
            adj[u] = v

    node_to_service = {}
    for node in graph_data['nodes']:
        if 'id' in node and 'source_file' in node:
            f = node['source_file'].replace("\\", "/")
            parts = f.split('/')
            service = "/".join(parts[:2]) if len(parts) > 1 else "root"
            node_to_service[node['id']] = service

    for item in graph_data['nodes']:
        if 'source' in item and 'target' in item:
            u, v = item['source'], item['target']
            u_service = node_to_service.get(u)
            v_service = node_to_service.get(v)
            if u_service and v_service and u_service != v_service:
                services[u_service]["dependencies"].add(v_service)
                services[v_service]["dependents"].add(u_service)

    # 3. Generate Markdown
    lines = ["# Service Ownership & Dependency Map", ""]
    lines.append("| Service | File Count | Dependencies | Dependents |")
    lines.append("| :--- | :--- | :--- | :--- |")
    
    sorted_services = sorted(services.keys(), key=lambda x: len(services[x]["files"]), reverse=True)
    
    for s in sorted_services:
        f_count = len(services[s]["files"])
        deps = ", ".join(sorted(list(services[s]["dependencies"])))
        dep_by = ", ".join(sorted(list(services[s]["dependents"])))
        lines.append(f"| `{s}` | {f_count} | {deps} | {dep_by} |")
    
    lines.append("\n## Critical Service Paths")
    # Simple logic: Services with many dependents are critical
    critical = sorted(services.keys(), key=lambda x: len(services[x]["dependents"]), reverse=True)[:5]
    for c in critical:
        lines.append(f"- **{c}**: Critical dependency for {len(services[c]['dependents'])} other services.")

    with open(OUTPUT_PATH, 'w') as f:
        f.write("\n".join(lines))
    
    print(f"Service Map generated at {OUTPUT_PATH}")

if __name__ == "__main__":
    generate_service_map(load_graph())
