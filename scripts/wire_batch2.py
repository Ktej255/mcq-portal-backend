#!/usr/bin/env python3
"""Phase 4 batch 2: wire rich topics 19-22 into Geomorphology.

- New sub-topic "Geomorphic Processes": 19 Weathering, 20 Mass Wasting
- New sub-topic "Landforms": 21 Fluvial Landforms, 22 Karst Topography
Removes the plain duplicate leaves these replace from the
"Geomorphology — Additional Topics (pending upgrade)" bucket.

Backup written before changes. Usage: python scripts/wire_batch2.py
"""
from __future__ import annotations
import glob, json, os, shutil
from datetime import datetime

HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, "..", "app", "core", "gs_lms", "data")
SEED = os.path.join(DATA, "gs_geography_syllabus.json")
UPGRADED_DIR = os.path.join(DATA, "upgraded_topics")

LEAF_FIELDS = ("title", "node_type", "weight", "content_sections", "pyqs",
               "mcq_questions", "concept_checklist", "ordering_justification", "video_url")

NEW_SUBS = [
    ("Geomorphic Processes", ["19", "20"]),
    ("Landforms", ["21", "22"]),
]
# Plain leaf titles (in pending bucket) now replaced by rich topics — remove them.
REMOVE_TITLES = {
    "Denudation, Physical & Chemical Weathering",
    "Mass Wasting and Indian Landslides",
    "Fluvial Geomorphology – Youthful & Mature Stages",
    "Deltas, Rejuvenation, and Stream Piracy",
    "Karst Topography and Limestone Landforms",
}


def load_by_num():
    by = {}
    for p in sorted(glob.glob(os.path.join(UPGRADED_DIR, "*.json"))):
        by[os.path.basename(p).split("_", 1)[0]] = json.load(open(p, encoding="utf-8"))
    return by


def make_leaf(up, order):
    leaf = {"display_order": order}
    for f in LEAF_FIELDS:
        if f in up:
            leaf[f] = up[f]
    leaf["node_type"] = "LEAF_TOPIC"
    leaf["review_status"] = "REVIEWED"
    return leaf


def main():
    up = load_by_num()
    seed = json.load(open(SEED, encoding="utf-8"))
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy2(SEED, SEED + f".{stamp}.bak")
    print(f"Backup: gs_geography_syllabus.json.{stamp}.bak")

    geo = next(n for n in seed["tree"] if n.get("title") == "Geomorphology")
    subs = geo.setdefault("children", [])

    # Find the pending bucket and the Earthquakes sub-topic order.
    pending = next((s for s in subs if "pending upgrade" in (s.get("title") or "")), None)
    base_order = max((s.get("display_order", 0) for s in subs), default=0)

    # Remove plain duplicate leaves from the pending bucket.
    if pending:
        before = len(pending.get("children", []))
        pending["children"] = [c for c in pending.get("children", [])
                               if (c.get("title") or "").strip() not in REMOVE_TITLES]
        print(f"Removed {before - len(pending['children'])} duplicate plain leaves from pending bucket")

    # Add the new rich sub-topics just before the pending bucket.
    new_nodes = []
    for i, (title, nums) in enumerate(NEW_SUBS, start=1):
        new_nodes.append({
            "title": title,
            "node_type": "SUB_TOPIC",
            "display_order": base_order + i,
            "children": [make_leaf(up[n], j + 1) for j, n in enumerate(nums)],
        })
        print(f"Added sub-topic '{title}' with {len(nums)} rich topics")

    # Push the pending bucket to the end.
    if pending:
        pending["display_order"] = base_order + len(NEW_SUBS) + 1

    subs.extend(new_nodes)
    json.dump(seed, open(SEED, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("Seed updated.")


if __name__ == "__main__":
    main()
