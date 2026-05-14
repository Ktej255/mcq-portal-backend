import ast
import os
import json
from pathlib import Path

class GraphExtractor:
    def __init__(self, root_dir):
        self.root_dir = Path(root_dir)
        self.graph = {
            "files": {},
            "dependencies": [],
            "concepts": {}
        }

    def analyze_python_file(self, file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            try:
                tree = ast.parse(f.read())
            except Exception as e:
                print(f"Error parsing {file_path}: {e}")
                return

        rel_path = str(file_path.relative_to(self.root_dir)).replace("\\", "/")
        self.graph["files"][rel_path] = {
            "classes": [],
            "functions": [],
            "imports": []
        }

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                self.graph["files"][rel_path]["classes"].append(node.name)
            elif isinstance(node, ast.FunctionDef):
                self.graph["files"][rel_path]["functions"].append(node.name)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self.graph["files"][rel_path]["imports"].append(alias.name)
                else:
                    module = node.module or ""
                    for alias in node.names:
                        self.graph["files"][rel_path]["imports"].append(f"{module}.{alias.name}")

    def analyze_typescript_file(self, file_path):
        rel_path = str(file_path.relative_to(self.root_dir)).replace("\\", "/")
        self.graph["files"][rel_path] = {
            "exports": [],
            "imports": [],
            "api_endpoints": []
        }
        
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            # Naive regex for imports and service calls
            import_matches = re.findall(r'import .* from [\'"](.*)[\'"]', content)
            self.graph["files"][rel_path]["imports"].extend(import_matches)
            
            # Look for API endpoint strings
            endpoint_matches = re.findall(r'[\'"](reports/.*|dashboard/.*|attempts/.*|simulation/.*)[\'"]', content)
            self.graph["files"][rel_path]["api_endpoints"].extend(list(set(endpoint_matches)))

    def crawl(self):
        excluded = {".next", "node_modules", ".git", "__pycache__", "venv", ".pytest_cache"}
        for root, dirs, files in os.walk(self.root_dir):
            dirs[:] = [d for d in dirs if d not in excluded]
            for file in files:
                full_path = Path(root) / file
                if file.endswith(".py"):
                    self.analyze_python_file(full_path)
                elif file.endswith((".ts", ".tsx")):
                    self.analyze_typescript_file(full_path)

    def generate_dependencies(self):
        # Python dependencies
        for file, data in self.graph["files"].items():
            if file.endswith(".py"):
                for imp in data.get("imports", []):
                    if "app." in imp:
                        self.graph["dependencies"].append({
                            "source": file,
                            "target": imp,
                            "type": "python_import"
                        })
            elif file.endswith((".ts", ".tsx")):
                for imp in data.get("imports", []):
                    if imp.startswith("@/"):
                        self.graph["dependencies"].append({
                            "source": file,
                            "target": imp,
                            "type": "typescript_import"
                        })
                for endpoint in data.get("api_endpoints", []):
                    self.graph["dependencies"].append({
                        "source": file,
                        "target": endpoint,
                        "type": "api_interaction"
                    })

    def save(self, output_path):
        with open(output_path, "w") as f:
            json.dump(self.graph, f, indent=2)

if __name__ == "__main__":
    import re
    extractor = GraphExtractor(".")
    extractor.crawl()
    extractor.generate_dependencies()
    extractor.save("docs/governance/ARCHITECTURE_GRAPH.json")
    print("Graph extraction complete.")

