#!/usr/bin/env python3
"""Remove plain sub-topics now superseded by the rich 'Geomorphic Processes'
and 'Landforms' sub-topics. Distinct plain leaves worth keeping are moved into
the pending-upgrade bucket; direct duplicates are dropped.

Backup written before changes. Usage: python scripts/cleanup_dupe_subtopics.py
"""
from __future__ import annotations
import json, os, shutil
from datetime import datetime

HERE = os.path.dirname(__file__)
SEED = os.path.join(HERE, "..", "app", "core", "gs_lms", "data", "gs_geography_syllabus.json")

# Plain sub-topics superseded by the new rich sub-topics.
SUPERSEDED_SUBS = {"Weathering and Mass Wasting", "Karst Topography", "Fluvial Landforms"}
# Direct-duplicate leaf titles to DROP (covered by rich 19-22).
DROP_LEAVES = {
    "Denudation, Physical & Chemical Weathering",
    "Mass Wasting and Indian Landslides",
    "Karst Topography and Limestone Landforms",
    "Fluvial Geomorphology – Youthful & Mature Stages",
    "Deltas, Rejuvenation, and Stream Piracy",
}


def main():
    seed = json.load(open(SEED, encoding="utf-8"))
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy2(SEED, SEED + f".{stamp}.bak")
    print(f"Backup: gs_geography_syllabus.json.{stamp}.bak")

    geo = next(n for n in seed["tree"] if n.get("title") == "Geomorphology")
    subs = geo["children"]
    pending = next((s for s in subs if "pending upgrade" in (s.get("title") or "")), None)

    kept_distinct = []
    new_subs = []
    for s in subs:
        if s.get("title") in SUPERSEDED_SUBS:
            # Keep any non-duplicate leaves by moving them to pending.
            for c in s.get("children", []):
                if (c.get("title") or "").strip() not in DROP_LEAVES:
                    kept_distinct.append(c)
            print(f"Removed superseded sub-topic '{s['title']}' (kept {sum(1 for c in s.get('children',[]) if (c.get('title') or '').strip() not in DROP_LEAVES)} distinct leaves)")
        else:
            new_subs.append(s)

    if pending and kept_distinct:
        base = len(pending.get("children", []))
        for i, c in enumerate(kept_distinct, start=base + 1):
            c["display_order"] = i
        pending["children"].extend(kept_distinct)
        print(f"Moved {len(kept_distinct)} distinct plain leaves into pending bucket")

    geo["children"] = new_subs
    json.dump(seed, open(SEED, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("Seed updated.")


if __name__ == "__main__":
    main()
