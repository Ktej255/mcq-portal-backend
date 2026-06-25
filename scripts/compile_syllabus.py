import json
import shutil
from pathlib import Path

# Paths
BACKEND_DIR = Path(__file__).resolve().parent.parent
GENERATED_DIR = BACKEND_DIR / "scripts" / "generated_lectures"
FINAL_SYLLABUS_PATH = BACKEND_DIR / "app" / "core" / "gs_lms" / "data" / "gs_geography_syllabus.json"
BACKUP_SYLLABUS_PATH = BACKEND_DIR / "app" / "core" / "gs_lms" / "data" / "gs_geography_syllabus_backup.json"

# Hierarchy mapping for the 47 lectures
HIERARCHY = {
    "Geomorphology": {
        "Earth's Origin and Interior": [1, 3, 10, 11, 12, 13, 14],
        "Physical Geography Basics": [2],
        "Continental Drift and Plate Tectonics": [4, 5, 6, 7, 8, 9],
        "Drainage Systems": [15],
        "Weathering and Mass Wasting": [16, 17, 18, 19],
        "Karst Topography": [20],
        "Fluvial Landforms": [21, 22]
    },
    "Climatology & Oceanography": {
        "Climatology": [23, 24, 25, 26, 27, 28, 29, 30, 31],
        "Oceanography": [32, 33, 34, 35]
    },
    "Human, Models & Indian Geography": {
        "Geographical Models & Theories": [36, 37, 38, 39],
        "Economic & Indian Geography": [40, 41, 42, 43, 44, 45, 46, 47]
    }
}

def main():
    print("Compiling geography syllabus...")
    
    # Back up the existing syllabus file if it exists and backup doesn't already exist
    if FINAL_SYLLABUS_PATH.exists():
        if not BACKUP_SYLLABUS_PATH.exists():
            shutil.copy(FINAL_SYLLABUS_PATH, BACKUP_SYLLABUS_PATH)
            print(f"Backed up original syllabus to: {BACKUP_SYLLABUS_PATH}")
        else:
            print("Backup already exists, skipping backup creation.")

    tree = []
    mega_order = 1
    
    for mega_title, subtopics in HIERARCHY.items():
        mega_node = {
            "title": mega_title,
            "node_type": "MEGA_TOPIC",
            "display_order": mega_order,
            "children": []
        }
        mega_order += 1
        
        sub_order = 1
        for sub_title, lecture_ids in subtopics.items():
            sub_node = {
                "title": sub_title,
                "node_type": "SUB_TOPIC",
                "display_order": sub_order,
                "children": []
            }
            sub_order += 1
            
            leaf_order = 1
            for lec_id in lecture_ids:
                lec_file = GENERATED_DIR / f"lecture_{lec_id}.json"
                if not lec_file.exists():
                    print(f"WARNING: Generated file not found for Lecture {lec_id} ({lec_file.name})")
                    # Create a placeholder if not generated yet, to maintain structure
                    leaf_node = {
                        "title": f"Lecture {lec_id}: Pending Generation",
                        "node_type": "LEAF_TOPIC",
                        "weight": 1.0,
                        "display_order": leaf_order,
                        "content_sections": [
                            {
                                "section_label": "BASIC",
                                "title": "Pending content",
                                "display_order": 1,
                                "authored": False,
                                "blocks": [{"type": "para", "text": "Content generation pending."}]
                            }
                        ],
                        "pyqs": [],
                        "mcq_questions": []
                    }
                else:
                    with open(lec_file, "r", encoding="utf-8") as f:
                        lec_data = json.load(f)
                    
                    # Ensure weight is present
                    weight = lec_data.get("weight", 1.0)
                    
                    # Fix display order to be local relative to sibling leaves
                    leaf_node = {
                        "title": lec_data["title"],
                        "node_type": "LEAF_TOPIC",
                        "weight": weight,
                        "display_order": leaf_order,
                        "content_sections": lec_data.get("content_sections", []),
                        "pyqs": lec_data.get("pyqs", []),
                        "mcq_questions": lec_data.get("mcq_questions", [])
                    }
                
                sub_node["children"].append(leaf_node)
                leaf_order += 1
                
            mega_node["children"].append(sub_node)
            
        tree.append(mega_node)
        
    syllabus_data = {
        "subject_id": 1,
        "tree": tree
    }
    
    with open(FINAL_SYLLABUS_PATH, "w", encoding="utf-8") as f:
        json.dump(syllabus_data, f, indent=2, ensure_ascii=False)
        
    print(f"Successfully compiled and saved 47-lecture syllabus to: {FINAL_SYLLABUS_PATH}")

if __name__ == "__main__":
    main()
