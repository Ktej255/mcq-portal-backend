from __future__ import annotations

import hashlib
from typing import Any

from app.services.strategy_registry import get_strategy

EXPERIMENT_VERSION = "adaptive-experimentation.v1"

EXPERIMENTS = {
    "revision_intensity_v1": {
        "experiment_id": "revision_intensity_v1",
        "purpose": "Compare low vs medium revision intensity under low-risk conditions.",
        "variants": {
            "A": {"strategy_id": "low_intensity_recovery", "revision_intensity": "LOW"},
            "B": {"strategy_id": "revision_reinforcement", "revision_intensity": "MEDIUM"},
        },
        "risk": "LOW",
    },
    "pacing_strategy_v1": {
        "experiment_id": "pacing_strategy_v1",
        "purpose": "Compare standard vs buffered pacing recommendations.",
        "variants": {
            "A": {"strategy_id": "low_intensity_recovery", "pace_buffer": 0},
            "B": {"strategy_id": "fatigue_sensitive_pacing", "pace_buffer": 15},
        },
        "risk": "LOW",
    },
}


def assign_experiment(user_id: int, experiment_id: str, reliability: dict[str, Any]) -> dict[str, Any]:
    experiment = EXPERIMENTS[experiment_id]
    if experiment["risk"] != "LOW" or reliability.get("mode") == "ASSERTIVE_BUT_REVERSIBLE":
        allowed = True
    else:
        allowed = reliability.get("recommendation_confidence", 0) >= 0.25
    if not allowed:
        return {
            "experiment_id": experiment_id,
            "assigned": False,
            "reason": "Reliability too low for experimentation.",
            "metric_version": EXPERIMENT_VERSION,
        }
    digest = hashlib.sha256(f"{user_id}:{experiment_id}".encode("utf-8")).hexdigest()
    variant_id = "A" if int(digest, 16) % 2 == 0 else "B"
    variant = experiment["variants"][variant_id]
    return {
        "experiment_id": experiment_id,
        "variant_id": variant_id,
        "assigned": True,
        "strategy": get_strategy(variant["strategy_id"]),
        "variant": variant,
        "risk": experiment["risk"],
        "metric_version": EXPERIMENT_VERSION,
    }


def experiment_observability(assignments: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(assignments)
    assigned = len([item for item in assignments if item.get("assigned")])
    low_confidence = len([item for item in assignments if not item.get("assigned")])
    return {
        "assignment_count": total,
        "assigned_rate": round((assigned / total * 100), 4) if total else 0,
        "low_confidence_exclusion_rate": round((low_confidence / total * 100), 4) if total else 0,
        "metric_version": EXPERIMENT_VERSION,
    }
