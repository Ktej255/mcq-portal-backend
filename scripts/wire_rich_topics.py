#!/usr/bin/env python3
"""Phase 1: wire the 12 authored rich topics (07-18) into the Geomorphology tree.

- 07-10  -> sub-topic "Earth's Origin and Interior"
- 11-14  -> sub-topic "Continental Drift and Plate Tectonics"
- 15-18  -> new sub-topic "Earthquakes and Volcanism"

Displaced plain leaves are preserved under a new sub-topic
"Geomorphology — Additional Topics (pending upgrade)" so no coverage is lost.

A timestamped backup is written before any change.
Usage: python scripts/wire_rich_topics.py
"""
from __future__ import annotations
import glob, json, os, shutil
from datetime import datetime

HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, "..", "app", "core", "gs_lms", "data")
SEED = os.path.join(DATA, "gs_geography_syllabus.json")
UPGRADED_DIR = os.path.join(DATA, "upgraded_topics")

# Fields copied from an upgraded file into the leaf node placed in the tree.
LEAF_FIELDS = (
    "title", "node_type", "weight", "content_sections", "pyqs",
    "mcq_questions", "concept_checklist", "ordering_justification", "video_url",
)

# Which upgraded file numbers go under which sub-topic title.
PLACEMENT = {
    "Earth's Origin and Interior": ["07", "08", "09", "10"],
    "Continental Drift and Plate Tectonics": ["11", "12", "13", "14"],
}
NEW_SUB_TITLE = "Earthquakes and Volcanism"
NEW_SUB_FILES = ["15", "16", "17", "18"]
PENDING_SUB_TITLE = "Geomorphology — Additional Topics (pending upgrade)"


def load_upgraded_by_num() -> dict[str, dict]:
    by_num: dict[str, dict] = {}
    for path in sorted(glob.glob(os.path.join(UPGRADED_DIR, "*.json"))):
        base = os.path.basename(path)
        num = base.split("_", 1)[0]
        by_num[num] = json.load(open(path, encoding="utf-8"))
    return by_num


def make_leaf(up: dict, order: int) -> dict:
    leaf = {"display_order": order}
    for f in LEAF_FIELDS:
        if f in up:
            leaf[f] = up[f]
    leaf["node_type"] = "LEAF_TOPIC"
    leaf["review_status"] = "REVIEWED"
    return leaf


def main() -> None:
    up = load_upgraded_by_num()
    seed = json.load(open(SEED, encoding="utf-8"))

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = SEED + f".{stamp}.bak"
    shutil.copy2(SEED, backup)
    print(f"Backup written: {os.path.basename(backup)}")

    # Find Geomorphology mega.
    geo = next(n for n in seed["tree"] if n.get("title") == "Geomorphology")
    subs = geo.setdefault("children", [])

    displaced: list[dict] = []

    # Replace children of the targeted sub-topics with rich leaves.
    for sub in subs:
        title = sub.get("title")
        if title in PLACEMENT:
            displaced.extend(sub.get("children") or [])
            nums = PLACEMENT[title]
            sub["children"] = [make_leaf(up[n], i + 1) for i, n in enumerate(nums)]
            print(f"Wired {len(nums)} rich topics into '{title}'")

    # Determine display_order for the new sub-topic (after Plate Tectonics).
    pt = next((s for s in subs if s.get("title") == "Continental Drift and Plate Tectonics"), None)
    insert_order = (pt.get("display_order", len(subs)) if pt else len(subs)) + 1

    # Build the new Earthquakes and Volcanism sub-topic.
    eq_sub = {
        "title": NEW_SUB_TITLE,
        "node_type": "SUB_TOPIC",
        "display_order": insert_order,
        "children": [make_leaf(up[n], i + 1) for i, n in enumerate(NEW_SUB_FILES)],
    }

    # Bump display_order of subs that come at/after the insert position.
    for s in subs:
        if s.get("display_order", 0) >= insert_order:
            s["display_order"] = s.get("display_order", 0) + 1
    subs.append(eq_sub)
    print(f"Added new sub-topic '{NEW_SUB_TITLE}' with {len(NEW_SUB_FILES)} rich topics")

    # Preserve displaced plain leaves under a pending sub-topic.
    if displaced:
        max_order = max((s.get("display_order", 0) for s in subs), default=0)
        for i, leaf in enumerate(displaced, start=1):
            leaf["display_order"] = i
        pending = {
            "title": PENDING_SUB_TITLE,
            "node_type": "SUB_TOPIC",
            "display_order": max_order + 1,
            "children": displaced,
        }
        subs.append(pending)
        print(f"Preserved {len(displaced)} plain leaves under '{PENDING_SUB_TITLE}'")

    json.dump(seed, open(SEED, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("Seed updated.")


if __name__ == "__main__":
    main()
