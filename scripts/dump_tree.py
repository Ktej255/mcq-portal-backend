#!/usr/bin/env python3
"""Print the full syllabus tree hierarchy with node types and display_order."""
import json, os
HERE = os.path.dirname(__file__)
SEED = os.path.join(HERE, "..", "app", "core", "gs_lms", "data", "gs_geography_syllabus.json")
seed = json.load(open(SEED, encoding="utf-8"))

def walk(nodes, depth=0):
    for n in sorted(nodes, key=lambda x: x.get("display_order", 0)):
        nt = n.get("node_type", "?")[:4]
        has_rich = ""
        if n.get("node_type") == "LEAF_TOPIC":
            secs = n.get("content_sections") or []
            mcqs = n.get("mcq_questions") or []
            # detect rich: any non-para block
            rich = any(
                b.get("type") not in ("para", None)
                for s in secs for b in (s.get("blocks") or [])
            )
            has_rich = f"  [{'RICH' if rich else 'plain'}, {len(mcqs)} mcq, {len(secs)} sec]"
        print(f"{'  '*depth}{n.get('display_order',0):>2}. ({nt}) {n.get('title')}{has_rich}")
        walk(n.get("children") or [], depth+1)

walk(seed.get("tree", []))
