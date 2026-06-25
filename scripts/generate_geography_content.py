import os
import sys
import json
from pathlib import Path
import google.generativeai as genai

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# API Key config
api_key = "AIzaSyBIRQsLwhooqdPe7K46-e7Wqxpk_I-Fi7w"
genai.configure(api_key=api_key)

# File paths
KB_PATH = Path(__file__).resolve().parent.parent / "app" / "core" / "optional" / "data" / "geography_reference_kb.json"
STEERING_PATH = Path(__file__).resolve().parent.parent.parent / ".kiro" / "steering" / "content-creation-framework.md"
OUTPUT_DIR = Path(__file__).resolve().parent / "generated_lectures"
OUTPUT_DIR.mkdir(exist_ok=True)

# Master list of Lectures with keyword mappings for retrieval
LECTURES = {
    1: {
        "title": "Earth's Origin, Structure, and Shield Areas",
        "keywords": ["origin and evolution of earth", "aravalli", "peninsular plateau", "shield"],
        "subtopic": "Earth's Origin and Interior"
    },
    2: {
        "title": "Straits, Isthmuses, and Inland Waterways",
        "keywords": ["strait", "isthmus", "waterway", "canal"],
        "subtopic": "Physical Geography Basics"
    },
    3: {
        "title": "Geological Time Scale, Coal, and Deccan Basalt",
        "keywords": ["geological time scale", "coal", "basalt", "cretaceous"],
        "subtopic": "Earth's Origin and Interior"
    },
    4: {
        "title": "Continental Drift Theory (Wegener)",
        "keywords": ["continental drift", "wegener", "pangea", "tethys"],
        "subtopic": "Continental Drift and Plate Tectonics"
    },
    5: {
        "title": "Plate Tectonics – Divergent Boundaries",
        "keywords": ["divergent", "mid-oceanic ridge", "rift valley"],
        "subtopic": "Continental Drift and Plate Tectonics"
    },
    6: {
        "title": "Plate Tectonics – Convergent Boundaries (Ocean-Continental)",
        "keywords": ["convergent", "subduction", "rockies", "andes", "ring of fire"],
        "subtopic": "Continental Drift and Plate Tectonics"
    },
    7: {
        "title": "Plate Tectonics – Convergent Boundaries (Ocean-Ocean & Trijunctions)",
        "keywords": ["ocean-ocean", "island arc", "trench", "indonesian"],
        "subtopic": "Continental Drift and Plate Tectonics"
    },
    8: {
        "title": "Plate Tectonics – Continent-Continent Collision (Himalayas)",
        "keywords": ["collision", "himalaya", "uplift", "obduction"],
        "subtopic": "Continental Drift and Plate Tectonics"
    },
    9: {
        "title": "Ocean-Ocean Convergence and Island Arcs",
        "keywords": ["ocean-ocean", "island arc", "trench", "mariana", "aleutian"],
        "subtopic": "Continental Drift and Plate Tectonics"
    },
    10: {
        "title": "Folding and Faulting",
        "keywords": ["folding", "faulting", "horst", "graben", "nappe"],
        "subtopic": "Earth's Origin and Interior"
    },
    11: {
        "title": "Rift Valleys and Block Mountains",
        "keywords": ["rift valley", "narmada", "tapi", "vindhya", "satpura"],
        "subtopic": "Earth's Origin and Interior"
    },
    12: {
        "title": "Intrusive & Extrusive Volcanism",
        "keywords": ["volcano", "intrusive", "batholith", "sill", "dyke"],
        "subtopic": "Earth's Origin and Interior"
    },
    13: {
        "title": "Hydrothermal Features & Petrology",
        "keywords": ["hot spring", "geyser", "fumarole", "rock"],
        "subtopic": "Earth's Origin and Interior"
    },
    14: {
        "title": "Rock Cycle and Drainage Introduction",
        "keywords": ["rock cycle", "archean", "alluvial", "drainage"],
        "subtopic": "Earth's Origin and Interior"
    },
    15: {
        "title": "Indian Drainage Systems and Drainage Patterns",
        "keywords": ["drainage pattern", "trellised", "dendritic", "radial", "sequent", "antecedent"],
        "subtopic": "Drainage Systems"
    },
    16: {
        "title": "Denudation, Physical & Chemical Weathering",
        "keywords": ["denudation", "weathering", "physical weathering", "chemical weathering"],
        "subtopic": "Weathering and Mass Wasting"
    },
    17: {
        "title": "Mass Wasting and Indian Landslides",
        "keywords": ["mass movement", "creep", "flow", "landslide", "western ghats"],
        "subtopic": "Weathering and Mass Wasting"
    },
    18: {
        "title": "Landslide Disaster Management & Mitigation",
        "keywords": ["landslide", "mitigation", "disaster management", "gsi"],
        "subtopic": "Weathering and Mass Wasting"
    },
    19: {
        "title": "Himalayan Landslide Vulnerability",
        "keywords": ["landslide", "himalaya", "cloudburst", "isostatic"],
        "subtopic": "Weathering and Mass Wasting"
    },
    20: {
        "title": "Karst Topography and Limestone Landforms",
        "keywords": ["karst", "limestone", "sinkhole", "stalactite", "stalagmite"],
        "subtopic": "Karst Topography"
    },
    21: {
        "title": "Fluvial Geomorphology – Youthful & Mature Stages",
        "keywords": ["fluvial", "pothole", "gorge", "alluvial fan", "bhabhar", "terai", "meander"],
        "subtopic": "Fluvial Landforms"
    },
    22: {
        "title": "Deltas, Rejuvenation, and Stream Piracy",
        "keywords": ["delta", "rejuvenation", "knick point", "river capture", "stream piracy"],
        "subtopic": "Fluvial Landforms"
    },
    23: {
        "title": "Structure and Composition of Atmosphere",
        "keywords": ["atmosphere", "troposphere", "stratosphere", "ionosphere", "composition"],
        "subtopic": "Climatology"
    },
    24: {
        "title": "Solar Radiation and Heat Budget of Earth",
        "keywords": ["heat budget", "solar radiation", "insolation", "albedo"],
        "subtopic": "Climatology"
    },
    25: {
        "title": "Temperature Distribution and Inversions",
        "keywords": ["temperature distribution", "temperature inversion", "lapse rate"],
        "subtopic": "Climatology"
    },
    26: {
        "title": "Atmospheric Pressure Belts and Winds",
        "keywords": ["pressure belt", "coriolis force", "planetary wind", "trade wind"],
        "subtopic": "Climatology"
    },
    27: {
        "title": "Jet Streams and Tricellular Circulation",
        "keywords": ["jet stream", "hadley cell", "ferrel cell", "polar cell", "tricellular"],
        "subtopic": "Climatology"
    },
    28: {
        "title": "Indian Monsoon Mechanism (El Nino, IOD, MJO)",
        "keywords": ["monsoon", "el nino", "la nina", "indian ocean dipole", "madden-julian"],
        "subtopic": "Climatology"
    },
    29: {
        "title": "Air Masses, Fronts, and Temperate Cyclones",
        "keywords": ["air mass", "front", "temperate cyclone", "extratropical"],
        "subtopic": "Climatology"
    },
    30: {
        "title": "Tropical Cyclones and Thunderstorms",
        "keywords": ["tropical cyclone", "thunderstorm", "hurricane", "typhoon"],
        "subtopic": "Climatology"
    },
    31: {
        "title": "Global Climatic Classifications (Koppen, Thornthwaite)",
        "keywords": ["koppen", "thornthwaite", "climatic classification"],
        "subtopic": "Climatology"
    },
    32: {
        "title": "Ocean Floor Relief (Atlantic, Pacific, Indian)",
        "keywords": ["ocean bottom", "continental shelf", "abyssal plain", "mid-ocean ridge", "trench"],
        "subtopic": "Oceanography"
    },
    33: {
        "title": "Temperature and Salinity of Oceans",
        "keywords": ["ocean temperature", "salinity", "thermocline"],
        "subtopic": "Oceanography"
    },
    34: {
        "title": "Waves, Tides, and Ocean Currents",
        "keywords": ["ocean current", "tide", "spring tide", "neap tide", "gulf stream", "kuroshio"],
        "subtopic": "Oceanography"
    },
    35: {
        "title": "Coral Reefs, Bleaching, and Marine Resources",
        "keywords": ["coral reef", "coral bleaching", "darwin", "marine resource", "eez"],
        "subtopic": "Oceanography"
    },
    36: {
        "title": "Agricultural Location Model (Von Thunen)",
        "keywords": ["von thunen", "agricultural location", "locational rent"],
        "subtopic": "Geographical Models & Theories"
    },
    37: {
        "title": "Industrial Location Theory (Weber)",
        "keywords": ["weber", "industrial location", "least cost", "isodapane"],
        "subtopic": "Geographical Models & Theories"
    },
    38: {
        "title": "Stages of Economic Growth (Rostow)",
        "keywords": ["rostow", "economic growth", "take-off"],
        "subtopic": "Geographical Models & Theories"
    },
    39: {
        "title": "Demographic Transition Model",
        "keywords": ["demographic transition", "birth rate", "death rate"],
        "subtopic": "Geographical Models & Theories"
    },
    40: {
        "title": "Factors of Industrial Location in South Asia",
        "keywords": ["industrial location", "south asia", "industry", "coal", "iron"],
        "subtopic": "Economic & Indian Geography"
    },
    41: {
        "title": "Mineral and Energy Resource Distribution in India",
        "keywords": ["mineral", "coal", "iron ore", "energy", "petroleum", "bauxite"],
        "subtopic": "Economic & Indian Geography"
    },
    42: {
        "title": "Indian Physiography and Geological Structure",
        "keywords": ["physiography", "peninsular plateau", "himalayas", "indo-gangetic plain"],
        "subtopic": "Economic & Indian Geography"
    },
    43: {
        "title": "Soils and Natural Vegetation of India",
        "keywords": ["soil", "forest", "vegetation", "champion and seth", "black soil", "alluvial"],
        "subtopic": "Economic & Indian Geography"
    },
    44: {
        "title": "Agriculture, Cropping Patterns, and Irrigation in India",
        "keywords": ["agriculture", "cropping pattern", "irrigation", "green revolution"],
        "subtopic": "Economic & Indian Geography"
    },
    45: {
        "title": "Population Dynamics and Urbanization in India",
        "keywords": ["population", "urbanization", "migration", "census"],
        "subtopic": "Economic & Indian Geography"
    },
    46: {
        "title": "Regional Planning and Sustainable Development in India",
        "keywords": ["regional planning", "sustainable development", "watershed", "hilly area"],
        "subtopic": "Economic & Indian Geography"
    },
    47: {
        "title": "Geopolitics and Boundary Issues of India",
        "keywords": ["geopolitics", "boundary", "border", "sir creek", "lac", "loc"],
        "subtopic": "Economic & Indian Geography"
    }
}

def load_kb():
    """Load reference knowledge base chunks."""
    if not KB_PATH.exists():
        return {"chunks": []}
    with open(KB_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def load_steering_rules():
    """Load the master content creation framework markdown."""
    if not STEERING_PATH.exists():
        return ""
    with open(STEERING_PATH, "r", encoding="utf-8") as f:
        return f.read()

def retrieve_relevant_chunks(lecture_id, kb):
    """Retrieve up to 5 relevant reference chunks for a given lecture based on keywords."""
    info = LECTURES.get(lecture_id)
    if not info:
        return []
        
    keywords = [k.lower() for k in info["keywords"]]
    chunks = kb.get("chunks", [])
    
    matched = []
    for chunk in chunks:
        chunk_text_lower = chunk["text"].lower()
        # Count keyword hits
        hits = sum(1 for kw in keywords if kw in chunk_text_lower)
        if hits > 0:
            matched.append((hits, chunk))
            
    # Sort by hits descending and take top 5
    matched.sort(key=lambda x: x[0], reverse=True)
    return [m[1] for m in matched[:5]]

def generate_lecture_content(lecture_id):
    """Generate high-quality grounded content for a single lecture."""
    lecture_info = LECTURES.get(lecture_id)
    if not lecture_info:
        print(f"Lecture {lecture_id} not defined in LECTURES dictionary.")
        return None
        
    print(f"Loading reference KB...")
    kb = load_kb()
    print(f"Loading steering rules...")
    steering_rules = load_steering_rules()
    
    print(f"Retrieving chunks for Lecture {lecture_id}: {lecture_info['title']}...")
    chunks = retrieve_relevant_chunks(lecture_id, kb)
    print(f"Retrieved {len(chunks)} relevant grounding chunks.")
    
    # Format chunks text for the prompt
    grounding_context = ""
    for idx, chunk in enumerate(chunks):
        grounding_context += f"\n--- REFERENCE SOURCE: {chunk['source']} (Chunk {idx+1}) ---\n{chunk['text']}\n"
        
    prompt = f"""
    You are the 'Geography Genius' content writing engine.
    Your task is to generate a comprehensive, exam-ready UPSC lesson block in JSON format for the following topic:
    
    Topic: Lecture {lecture_id}: {lecture_info['title']}
    Subtopic Area: {lecture_info['subtopic']}
    
    --- CONTENT CREATION FRAMEWORK & RULES ---
    {steering_rules}
    
    --- GROUNDING REFERENCE NOTES FROM CLASS ---
    Use the following real class lecture notes as the primary source of truth for facts, depth, and case studies:
    {grounding_context}
    
    --- OUTPUT FORMAT REQUIREMENT ---
    You MUST output a valid JSON object matching the following structure. Output ONLY the JSON block. Do not wrap in markdown code blocks like ```json.
    
    {{
      "title": "Lecture {lecture_id}: {lecture_info['title']}",
      "node_type": "LEAF_TOPIC",
      "display_order": {lecture_id},
      "content_sections": [
        {{
          "section_label": "BASIC",
          "title": "Fundamentals of {lecture_info['title']}",
          "display_order": 1,
          "authored": true,
          "blocks": [
            {{ "type": "para", "text": "..." }}
          ]
        }},
        {{
          "section_label": "ADVANCED",
          "title": "Advanced Analysis — {lecture_info['title']}",
          "display_order": 2,
          "authored": true,
          "blocks": [
            {{ "type": "para", "text": "..." }}
          ]
        }},
        {{
          "section_label": "NCERT_LEVEL",
          "title": "NCERT Reference — {lecture_info['title']}",
          "display_order": 3,
          "authored": true,
          "blocks": [
            {{ "type": "para", "text": "..." }}
          ]
        }},
        {{
          "section_label": "EXAMINER_TRAPS",
          "title": "Common Examiner Traps & Exam Strategy",
          "display_order": 4,
          "authored": true,
          "blocks": [
            {{ "type": "para", "text": "..." }}
          ]
        }}
      ]
    }}
    
    Ensure that the generated text paragraphs are highly detailed, factual, and strictly use 'UPSC statement style' (avoiding conversational filler).
    """
    
    # Use gemini-flash-latest
    model = genai.GenerativeModel("gemini-3.1-flash-lite")
    print(f"Calling Gemini to generate Lecture {lecture_id}...")
    response = model.generate_content(prompt)
    
    raw_text = response.text.strip()
    
    # Strip markdown wrappers if any
    if raw_text.startswith("```"):
        # find second index of ```
        raw_text = raw_text.strip("`").strip()
        if raw_text.startswith("json"):
            raw_text = raw_text[4:].strip()
            
    try:
        data = json.loads(raw_text)
        output_file = OUTPUT_DIR / f"lecture_{lecture_id}.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"Successfully generated and saved Lecture {lecture_id} to: {output_file}")
        return data
    except Exception as e:
        print(f"Failed to parse output as JSON. Error: {e}")
        print("Raw text returned:")
        print(raw_text[:1000])
        return None

if __name__ == "__main__":
    import time
    for lec_id in sorted(LECTURES.keys()):
        out_file = OUTPUT_DIR / f"lecture_{lec_id}.json"
        if out_file.exists():
            print(f"Lecture {lec_id} already exists. Skipping.")
            continue
        print(f"\n=========================================")
        print(f"Generating Lecture {lec_id}: {LECTURES[lec_id]['title']}")
        print(f"=========================================")
        data = generate_lecture_content(lec_id)
        if data is None:
            print(f"Failed to generate Lecture {lec_id}!")
        else:
            print(f"Successfully generated Lecture {lec_id}.")
        # Wait 5 seconds to stay safe from rate limits
        time.sleep(5)
