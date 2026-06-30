#!/usr/bin/env python3
"""Strip 'Lecture N:' prefixes from leaf titles and renumber display_order
sequentially within each parent, preserving the lecture-number ordering.

Writes a timestamped backup before modifying the seed.
Usage: python scripts/clean_lecture_titles.py
"""
from __future__ import annotations
import json, os, re, shutil
from datetime import datetime

HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, "..", "app", "core", "gs_lms", "data")
SEED = os.path.join(DATA, "gs_geography_syllabus.json")

LECTURE_RE = re.compile(r"^\s*Lecture\s+(\d+)\s*[:\-–]\s*(.+)$", re.IGNORECASE)


def clean_node(node: dict, stats: dict) -> int | None:
    """Clean a node's title. Returns the parsed lecture number (for ordering)."""
    title = (node.get("title") or "").strip()
    m = LECTURE_RE.match(title)
    lecture_num = None
    if m:
        lecture_num = int(m.group(1))
        node["title"] = m.group(2).strip()
        stats["stripped"] += 1
    return lecture_num


def process(nodes: list[dict], stats: dict) -> None:
    # First pass: clean titles and capture lecture numbers for ordering.
    numbered = []
    for n in nodes:
        ln = clean_node(n, stats)
        numbered.append((ln, n))

    # If any siblings had lecture numbers, reorder by them and assign
    # sequential display_order (1-based). Siblings without a number keep
    # their relative position after numbered ones.
    has_numbers = any(ln is not None for ln, _ in numbered)
    if has_numbers:
        numbered.sort(key=lambda t: (t[0] is None, t[0] if t[0] is not None else 0))
        for i, (ln, n) in enumerate(numbered, start=1):
            n["display_order"] = i
        # Re-write the children list in the new sorted order.
        nodes[:] = [n for _, n in numbered]

    # Recurse.
    for n in nodes:
        children = n.get("children") or []
        if children:
            process(children, stats)


def main() -> None:
    seed = json.load(open(SEED, encoding="utf-8"))
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = SEED + f".{stamp}.bak"
    shutil.copy2(SEED, backup)
    print(f"Backup written: {os.path.basename(backup)}")

    stats = {"stripped": 0}
    process(seed.get("tree", []), stats)

    json.dump(seed, open(SEED, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"Titles stripped of 'Lecture N:' prefix: {stats['stripped']}")


if __name__ == "__main__":
    main()
