"""Plan pricing — mirrors the frontend yearlyPlanner.ts.

Base monthly prices and multi-year discounts used to compute the amount to
charge for a (tier, billing_cycle) combination.
"""
from __future__ import annotations

from typing import Tuple

# Base monthly price per paid tier (INR). "free" is not purchasable.
TIER_BASE_MONTHLY = {
    "foundation": 399,
    "plus": 699,
    "pro": 999,
    "ultimate": 1299,
}

# cycle -> (months, discount_percent)
CYCLES = {
    "monthly": (1, 0),
    "yearly": (12, 15),
    "two-year": (24, 25),
    "three-year": (36, 35),
}


def compute_amount(tier: str, cycle: str) -> int:
    """Total amount (INR, rounded) to charge for the full billing cycle."""
    t = (tier or "").strip().lower()
    c = (cycle or "monthly").strip().lower()
    if t not in TIER_BASE_MONTHLY:
        raise ValueError(f"Unknown or non-purchasable tier: {tier}")
    if c not in CYCLES:
        raise ValueError(f"Unknown billing cycle: {cycle}")
    months, discount = CYCLES[c]
    list_price = TIER_BASE_MONTHLY[t] * months
    return round(list_price * (100 - discount) / 100)


def cycle_months(cycle: str) -> Tuple[int, int]:
    return CYCLES.get((cycle or "monthly").strip().lower(), (1, 0))
