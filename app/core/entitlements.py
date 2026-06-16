"""Server-side entitlements: tier -> capability limits, including the free entry tier.

Mirrors the frontend `src/lib/upsc/entitlements.ts`. No DB migration is required:
the default tier is "free". Once a subscription tier is persisted (on the User or a
related Subscription record), `entitlements` router resolves it instead of the default.

Tier prices (frontend yearlyPlanner.ts): free ₹0 · foundation ₹399 · plus ₹699 · pro ₹999 · ultimate ₹1299
"""
from __future__ import annotations

from typing import Optional

TIER_ORDER = ["free", "foundation", "plus", "pro", "ultimate"]

TIER_LABEL = {
    "free": "Free",
    "foundation": "Foundation",
    "plus": "Plus",
    "pro": "Pro",
    "ultimate": "Ultimate",
}

# None = unlimited
ENTITLEMENTS = {
    "free": {"daily_mcq_limit": 10, "daily_ai_minutes": 20, "weak_topic_runs": 1, "optional_subjects": False, "mains_upload": False, "unlimited_tests": False, "all_subjects": False},
    "foundation": {"daily_mcq_limit": 50, "daily_ai_minutes": 60, "weak_topic_runs": 1, "optional_subjects": False, "mains_upload": False, "unlimited_tests": False, "all_subjects": False},
    "plus": {"daily_mcq_limit": 200, "daily_ai_minutes": 180, "weak_topic_runs": 5, "optional_subjects": True, "mains_upload": False, "unlimited_tests": False, "all_subjects": True},
    "pro": {"daily_mcq_limit": None, "daily_ai_minutes": 360, "weak_topic_runs": None, "optional_subjects": True, "mains_upload": True, "unlimited_tests": True, "all_subjects": True},
    "ultimate": {"daily_mcq_limit": None, "daily_ai_minutes": None, "weak_topic_runs": None, "optional_subjects": True, "mains_upload": True, "unlimited_tests": True, "all_subjects": True},
}

DEFAULT_TIER = "free"


def normalize_tier(tier: Optional[str]) -> str:
    t = (tier or "").strip().lower()
    return t if t in ENTITLEMENTS else DEFAULT_TIER


def get_entitlements(tier: Optional[str]) -> dict:
    """Return a flat dict of capabilities for the given tier (or free if unknown)."""
    t = normalize_tier(tier)
    data = {"tier": t, "label": TIER_LABEL[t]}
    data.update(ENTITLEMENTS[t])
    return data


def next_tier(tier: Optional[str]) -> Optional[str]:
    t = normalize_tier(tier)
    i = TIER_ORDER.index(t)
    return TIER_ORDER[i + 1] if i < len(TIER_ORDER) - 1 else None


def is_mcq_limit_reached(used_today: int, tier: Optional[str]) -> bool:
    limit = get_entitlements(tier)["daily_mcq_limit"]
    return limit is not None and used_today >= limit
