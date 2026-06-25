import os
import sys
import json
import re
from pathlib import Path
from PyPDF2 import PdfReader
from docx import Document

# Add parent directory to path to use backend modules if needed
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Path configuration
REF_DIR = Path(r"D:\Graphology\Upsc 2027\June - Geography 2026\refernce")
OUTPUT_KB_PATH = Path(__file__).resolve().parent.parent / "app" / "core" / "optional" / "data" / "geography_reference_kb.json"

# Core Syllabus keywords map for categorization
SYLLABUS_CATEGORIES = {
    "Geomorphology - General & Forces": [
        "landform development", "endogenetic", "exogenetic", "diastrophism", "epeirogeny", 
        "orogeny", "denudation", "weathering", "mass wasting", "gradation", "degradation", "aggradation"
    ],
    "Earth's Interior & Crust": [
        "earth's interior", "geomagnetism", "seismology", "seismic waves", "moho", "discontinuity",
        "crust", "mantle", "core", "lithosphere", "asthenosphere", "shadow zone"
    ],
    "Continental Drift & Plate Tectonics": [
        "continental drift", "wegener", "pangea", "panthalassa", "sea floor spreading", "paleomagnetism",
        "plate tectonics", "subduction", "convergent", "divergent", "transform boundary", "convection current"
    ],
    "Isostasy": [
        "isostasy", "airy", "pratt", "hayford", "bowie", "heiskanen", "isostatic rebound", "compensation depth"
    ],
    "Mountain Building & Volcanism": [
        "mountain building", "orogenesis", "geosyncline", "kober", "jeffreys", "volcano", "vulcanicity",
        "lava", "magma", "batholith", "sill", "dyke", "hotspot", "mantle plume"
    ],
    "Earthquakes & Tsunamis": [
        "earthquake", "seismograph", "richter scale", "tsunami", "epicenter", "focus", "seismic hazard"
    ],
    "Geomorphic Cycles & Slopes": [
        "geomorphic cycle", "davis", "penck", "king", "slope development", "slope decline",
        "slope replacement", "parallel retreat", "peneplain", "pediplain", "etchplain", "denudation chronology"
    ],
    "Channel Morphology & Drainage": [
        "channel morphology", "drainage pattern", "drainage density", "stream order", "bifurcation ratio",
        "graded profile", "meander", "oxbow lake", "river terrace", "knickpoint", "hydraulic geometry"
    ],
    "Applied Geomorphology": [
        "applied geomorphology", "geohydrology", "landslide", "mass movement", "morphometric analysis",
        "gis", "remote sensing", "natural hazard", "watershed management"
    ],
    "Climatology - Atmosphere & Heat": [
        "atmosphere", "troposphere", "stratosphere", "ionosphere", "heat budget", "solar radiation",
        "insolation", "temperature inversion", "lapse rate", "greenhouse effect"
    ],
    "Atmospheric Circulation & Monsoons": [
        "atmospheric circulation", "hadley cell", "ferrel cell", "polar cell", "tricellular",
        "pressure belt", "coriolis force", "jet stream", "monsoon", "el nino", "la nina", "indian ocean dipole"
    ],
    "Air Masses, Fronts & Cyclones": [
        "air mass", "front", "frontogenesis", "cyclone", "anticyclone", "temperate cyclone",
        "tropical cyclone", "typhoon", "hurricane", "condensation", "precipitation"
    ],
    "Climatic Classification & Change": [
        "koppen", "thornthwaite", "trewartha", "climatic classification", "climate change",
        "global warming", "urban heat island", "anthropogenic", "ipcc"
    ],
    "Oceanography - Relief & T-S": [
        "ocean bottom", "continental shelf", "abyssal plain", "mid-ocean ridge", "trench",
        "atlantic ocean", "pacific ocean", "indian ocean", "ocean temperature", "salinity", "thermocline"
    ],
    "Ocean Currents & Tides": [
        "ocean current", "gulf stream", "kuroshio", "upwelling", "tide", "spring tide", "neap tide", "wave"
    ],
    "Coral Reefs & Marine Resources": [
        "coral reef", "fringing reef", "barrier reef", "atoll", "darwin", "daly", "coral bleaching",
        "marine resource", "eez", "polymetallic nodule"
    ]
}

def extract_pdf_text(path: Path) -> str:
    """Extract text from PDF using PyPDF2 with page number logging."""
    try:
        reader = PdfReader(path)
        text_parts = []
        num_pages = len(reader.pages)
        # For huge files, parse up to 500 pages to save memory and avoid timeout
        limit = min(num_pages, 500)
        for i in range(limit):
            page_text = reader.pages[i].extract_text()
            if page_text:
                text_parts.append(page_text)
        return "\n".join(text_parts)
    except Exception as e:
        print(f"Error reading PDF {path.name}: {e}")
        return ""

def extract_docx_text(path: Path) -> str:
    """Extract text from Word document."""
    try:
        doc = Document(path)
        return "\n".join([p.text for p in doc.paragraphs])
    except Exception as e:
        print(f"Error reading DOCX {path.name}: {e}")
        return ""

def categorise_and_chunk(filename: str, text: str) -> list:
    """Slices the text into semantic chunks and maps them to syllabus categories."""
    chunks = []
    # Split text into paragraphs
    paragraphs = [p.strip() for p in text.split("\n\n") if len(p.strip()) > 100]
    
    for i, para in enumerate(paragraphs):
        para_lower = para.lower()
        matched_categories = []
        
        # Check matching keywords
        for category, keywords in SYLLABUS_CATEGORIES.items():
            for keyword in keywords:
                if keyword in para_lower:
                    matched_categories.append(category)
                    break
        
        if matched_categories:
            chunks.append({
                "source": filename,
                "paragraph_index": i,
                "categories": matched_categories,
                "text": para[:1500]  # Limit chunk size to keep file size reasonable
            })
            
    return chunks

def main():
    print(f"Scanning references in: {REF_DIR}")
    if not REF_DIR.exists():
        print(f"Directory {REF_DIR} does not exist!")
        return
        
    all_chunks = []
    files = list(REF_DIR.glob("*"))
    
    # Prioritize smaller files and key PDFs
    for file_path in files:
        if file_path.is_dir():
            continue
            
        ext = file_path.suffix.lower()
        if ext not in [".pdf", ".docx"]:
            continue
            
        # Skip extremely large files to avoid out-of-memory or slowness (like the 242MB PPT)
        if file_path.stat().st_size > 180 * 1024 * 1024:
            print(f"Skipping giant file: {file_path.name} ({file_path.stat().st_size / 1024 / 1024:.1f} MB)")
            continue
            
        print(f"Processing: {file_path.name} ({file_path.stat().st_size / 1024 / 1024:.1f} MB)...")
        
        if ext == ".pdf":
            text = extract_pdf_text(file_path)
        else:
            text = extract_docx_text(file_path)
            
        if text:
            file_chunks = categorise_and_chunk(file_path.name, text)
            print(f"Generated {len(file_chunks)} chunks for {file_path.name}")
            all_chunks.extend(file_chunks)
            
    # Save the indexed knowledge base
    OUTPUT_KB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_KB_PATH, "w", encoding="utf-8") as f:
        json.dump({
            "generated_at": "2026-06-24",
            "total_chunks": len(all_chunks),
            "chunks": all_chunks
        }, f, indent=2, ensure_ascii=False)
        
    print(f"Reference Knowledge Base written successfully to: {OUTPUT_KB_PATH}")
    print(f"Total chunks stored: {len(all_chunks)}")

if __name__ == "__main__":
    main()
