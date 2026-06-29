#!/usr/bin/env python3
"""Merge upgraded topic JSON files into the GS Geography seed.

Each file in ``app/core/gs_lms/data/upgraded_topics/*.json`` is a single
LEAF_TOPIC node (v3-rich: content_sections + pyqs + mcq_questions +
concept_checklist). This script finds the matching leaf node in
``gs_geography_syllabus.json`` (by title) and replaces its authored fields,
so the upgraded content becomes the source of truth that the importer loads.

A timestamped backup of the seed is written before any change.

Usage: python scripts/merge_upgraded_topics.py
"""
from __future__ import annotations

import glob
import json
import os
import shutil
from datetime import datetime

HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, "..", "app", "core", "gs_lms", "data")
SEED = os.path.join(DATA, "gs_geography_syllabus.json")
UPGRADED_DIR = os.path.join(DATA, "upgraded_topics")

# Fields copied from an upgraded node onto the matching seed leaf node.
_FIELDS = (
    "content_sections",
    "pyqs",
    "mcq_questions",
    "concept_checklist",
    "weight",
    "display_order",
    "ordering_justification",
    "review_status",
    "video_url",
)


def load_upgraded() -> dict[str, dict]:
    """Map topic title -> upgraded node dict."""
    by_title: dict[str, dict] = {}
    for path in sorted(glob.glob(os.path.join(UPGRADED_DIR, "*.json"))):
        node = json.load(open(path, encoding="utf-8"))
        title = node.get("title")
        if title:
            by_title[title.strip()] = node
    return by_title


def apply_upgrades(nodes: list[dict], upgrades: dict[str, dict], stats: dict) -> None:
    for node in nodes:
        if node.get("node_type") == "LEAF_TOPIC":
            up = upgrades.get((node.get("title") or "").strip())
            if up is not None:
                for f in _FIELDS:
                    if f in up:
                        node[f] = up[f]
                stats["matched"] += 1
                stats["titles"].append(node["title"])
        children = node.get("children") or []
        if children:
            apply_upgrades(children, upgrades, stats)


def main() -> None:
    upgrades = load_upgraded()
    if not upgrades:
        print("No upgraded topic files found.")
        return

    seed = json.load(open(SEED, encoding="utf-8"))

    # Backup
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = SEED + f".{stamp}.bak"
    shutil.copy2(SEED, backup)
    print(f"Backup written: {os.path.basename(backup)}")

    stats = {"matched": 0, "titles": []}
    apply_upgrades(seed.get("tree", []), upgrades, stats)

    unique_titles = sorted(set(stats["titles"]))
    json.dump(seed, open(SEED, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    print(f"Upgraded topics available: {len(upgrades)}")
    print(f"Leaf nodes updated: {len(unique_titles)}")
    for t in unique_titles:
        print(f"  - {t}")
    missing = sorted(set(upgrades) - set(unique_titles))
    if missing:
        print("WARNING: these upgraded titles did NOT match any seed leaf:")
        for t in missing:
            print(f"  ! {t}")


if __name__ == "__main__":
    main()
