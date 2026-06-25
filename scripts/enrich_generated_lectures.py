import json
from pathlib import Path

# Paths
BACKEND_DIR = Path(__file__).resolve().parent.parent
GENERATED_DIR = BACKEND_DIR / "scripts" / "generated_lectures"

def enrich_lecture_15():
    lec_file = GENERATED_DIR / "lecture_15.json"
    if not lec_file.exists():
        print("WARNING: lecture_15.json not found!")
        return
        
    with open(lec_file, "r", encoding="utf-8") as f:
        d = json.load(f)
        
    modified = False
    
    # 1. Enrich ADVANCED section with Amarkantak radial drainage
    for section in d.get("content_sections", []):
        if section["section_label"] == "ADVANCED":
            # Check if already added
            if not any("Amarkantak" in b["text"] for b in section["blocks"]):
                section["blocks"].append({
                    "type": "para",
                    "text": "At a structural level, the Amarkantak Plateau, situated in the Maikal Hills of the Satpura Range, represents a key Biosphere Reserve and a prime example of a radial drainage system. From this plateau, the Narmada River flows westward into the Arabian Sea, while the Son River flows northward as a major tributary to the Ganga, demonstrating how geological uplifts control hydrological splitting."
                })
                modified = True
                
        # 2. Enrich BASIC section with Ganga distributaries
        if section["section_label"] == "BASIC":
            if not any("Hooghly" in b["text"] for b in section["blocks"]):
                section["blocks"].append({
                    "type": "para",
                    "text": "In the lower plains, the Ganga splits into distributaries, with the Hooghly River serving as the major distributary flowing through West Bengal into the Bay of Bengal, while the main branch (Padma) enters Bangladesh to join the Jamuna (Brahmaputra). The Damodar River also flows through this region, historically known as the 'Sorrow of Bengal' due to its devastating floods before river training."
                })
                modified = True
                
    if modified:
        with open(lec_file, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=2, ensure_ascii=False)
        print("Enriched Lecture 15 (Amarkantak & Hooghly/Damodar).")
    else:
        print("Lecture 15 already enriched.")

def enrich_lecture_21():
    lec_file = GENERATED_DIR / "lecture_21.json"
    if not lec_file.exists():
        print("WARNING: lecture_21.json not found!")
        return
        
    with open(lec_file, "r", encoding="utf-8") as f:
        d = json.load(f)
        
    modified = False
    
    for section in d.get("content_sections", []):
        if section["section_label"] == "ADVANCED":
            if not any("Shipki La" in b["text"] for b in section["blocks"]):
                section["blocks"].append({
                    "type": "para",
                    "text": "A classic example of antecedent drainage and youthful vertical incision in India is the Satluj River, which cuts a deep gorge through the Himalayas at Shipki La in Himachal Pradesh, maintaining its pre-uplift course through active downcutting."
                })
                modified = True
                
        if section["section_label"] == "BASIC":
            if not any("Traction Load" in b["text"] for b in section["blocks"]):
                section["blocks"].append({
                    "type": "para",
                    "text": "A river's transport capacity is categorized by load types: Traction Load consists of large pebbles and stones rolling or sliding along the riverbed; Suspension Load contains fine sand, silt, and clay suspended in the water column; and Solution Load comprises dissolved minerals. In the foothills, the coarse material forms the dry Bhabhar belt, while the emerging water creates the wet, marshy Terai grasslands, critical for agriculture and biodiversity."
                })
                modified = True
                
    if modified:
        with open(lec_file, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=2, ensure_ascii=False)
        print("Enriched Lecture 21 (Shipki La & Load categories).")
    else:
        print("Lecture 21 already enriched.")

def enrich_lecture_22():
    lec_file = GENERATED_DIR / "lecture_22.json"
    if not lec_file.exists():
        print("WARNING: lecture_22.json not found!")
        return
        
    with open(lec_file, "r", encoding="utf-8") as f:
        d = json.load(f)
        
    modified = False
    
    for section in d.get("content_sections", []):
        if section["section_label"] == "ADVANCED":
            if not any("Kanwar Lake" in b["text"] for b in section["blocks"]):
                section["blocks"].append({
                    "type": "para",
                    "text": "In the Indian landscape, Kanwar Lake in Bihar represents Asia's largest freshwater ox-bow lake, formed by the meandering dynamics of the Gandak River. It is a critical Ramsar site showing the ecological significance of fluvial abandonment."
                })
                section["blocks"].append({
                    "type": "para",
                    "text": "The physics of delta formation relates directly to relative fluid densities. An Arcuate Delta (e.g., Ganga-Brahmaputra, Nile) forms when river water density matches sea water density. A Bird-Foot Delta (e.g., Mississippi) develops when river water is less dense than sea water, allowing the fresh stream to penetrate deep into the basin before depositing fine clay. In contrast, an Estuarine Delta (e.g., Narmada, Tapi, Amazon) represents a submerged river valley where tectonic subsidence or high tidal range prevents depositional growth."
                })
                modified = True
                
    if modified:
        with open(lec_file, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=2, ensure_ascii=False)
        print("Enriched Lecture 22 (Kanwar Lake & Delta physics).")
    else:
        print("Lecture 22 already enriched.")

def enrich_lecture_30():
    lec_file = GENERATED_DIR / "lecture_30.json"
    if not lec_file.exists():
        print("WARNING: lecture_30.json not found!")
        return
        
    with open(lec_file, "r", encoding="utf-8") as f:
        d = json.load(f)
        
    modified = False
    
    for section in d.get("content_sections", []):
        if section["section_label"] == "ADVANCED":
            if not any("1888 India Hail Disaster" in b["text"] for b in section["blocks"]):
                section["blocks"].append({
                    "type": "para",
                    "text": "The physics of hailstorms requires strong, tilted updrafts in unstable air masses where lapse rates are steep. This allows hailstones to be recycled through freezing zones multiple times, accumulating water layers that freeze into concentric ice rings. Historically, the 1888 India Hail Disaster is one of the deadliest on record, causing close to 250 fatalities due to massive hailstone impacts."
                })
                section["blocks"].append({
                    "type": "para",
                    "text": "In northern India, Delhi-NCR's severe hailstorms are triggered by a wind confluence: moist air from the Bay of Bengal meets dry winds from the Arabian Sea, forced upward by jet streams aloft and coupled with cold temperatures brought by Western Disturbances, resulting in rapid convective instability."
                })
                modified = True
                
    if modified:
        with open(lec_file, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=2, ensure_ascii=False)
        print("Enriched Lecture 30 (Hailstorm physics & Delhi mechanism).")
    else:
        print("Lecture 30 already enriched.")

def main():
    print("Enriching lectures with PPT reference material...")
    enrich_lecture_15()
    enrich_lecture_21()
    enrich_lecture_22()
    enrich_lecture_30()
    print("Enrichment complete.")

if __name__ == "__main__":
    main()
