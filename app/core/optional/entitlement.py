"""Entitlement seam for the Optional Subjects Platform (Task 13.2 — R16).

A thin, swappable seam that decides whether a student may access a subject's
content. The real premium/entitlement engine currently lives on an unmerged
marketing branch (design "Entitlement seam"); until it is present this seam
returns a **safe, configurable default** so nothing crashes and wiring the real
engine later is config, not refactor.

Decision rules:
    * A subject is "premium" only when its ``config.premium`` flag is true.
      Non-premium subjects are always allowed (R16.3 — no gating where none is
      designated).
    * For a premium subject with no engine present, the default is configurable
      via ``OPTIONAL_ENTITLEMENT_DEFAULT_ALLOW`` (default ``true`` = open during
      early access). When set to ``false`` the seam restricts access and returns
      an ``upgrade_path`` (R16.2).

When the real engine is wired, add an ``EntitlementProvider`` that consults it
and select it via ``OPTIONAL_ENTITLEMENT_PROVIDER`` — the call sites
(``GET /optional/{slug}/access``) do not change.

Isolation (Requirement 2 / design Property 9): nothing here imports from or
references GS Geography (``/upsc/geography``) modules.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional

# Where to send a student who needs to upgrade for premium content (R16.2).
DEFAULT_UPGRADE_PATH = "/pricing"


@dataclass(frozen=True)
class EntitlementDecision:
    """The access decision for one (student, subject) pair (R16)."""

    allowed: bool
    premium: bool
    reason: str
    upgrade_path: Optional[str] = None


def _subject_is_premium(subject: Any) -> bool:
    config = getattr(subject, "config", None) or {}
    if not isinstance(config, dict):
        return False
    return bool(config.get("premium", False))


class EntitlementProvider(ABC):
    """Abstract entitlement decision-maker."""

    name: str = "abstract"

    @abstractmethod
    def check_access(self, *, student_id: int, subject: Any) -> EntitlementDecision:
        """Return the access decision for ``student_id`` + ``subject`` (R16)."""
        raise NotImplementedError


class DefaultEntitlementProvider(EntitlementProvider):
    """Safe-default entitlement seam used until the real engine is wired.

    Non-premium subjects are always allowed (R16.3). Premium subjects follow a
    configurable default (``default_allow``): open during early access, or
    restricted with an upgrade path when the founder flips the flag (R16.2).
    """

    name = "default"

    def __init__(self, default_allow: bool = True, upgrade_path: str = DEFAULT_UPGRADE_PATH):
        self.default_allow = default_allow
        self.upgrade_path = upgrade_path

    def check_access(self, *, student_id: int, subject: Any) -> EntitlementDecision:
        if not _subject_is_premium(subject):
            return EntitlementDecision(
                allowed=True,
                premium=False,
                reason="Open content — no entitlement required.",
                upgrade_path=None,
            )
        if self.default_allow:
            return EntitlementDecision(
                allowed=True,
                premium=True,
                reason="Premium content is open during early access.",
                upgrade_path=None,
            )
        return EntitlementDecision(
            allowed=False,
            premium=True,
            reason="This is premium content and requires an active subscription.",
            upgrade_path=self.upgrade_path,
        )


_PROVIDERS: dict = {}


def _env_default_allow() -> bool:
    raw = (os.environ.get("OPTIONAL_ENTITLEMENT_DEFAULT_ALLOW") or "true").strip().lower()
    return raw not in ("0", "false", "no", "off")


def get_entitlement_provider(name: Optional[str] = None) -> EntitlementProvider:
    """Return an :class:`EntitlementProvider`, selected by ``name`` or environment.

    Precedence: explicit ``name`` → ``OPTIONAL_ENTITLEMENT_PROVIDER`` env →
    ``"default"``. The default provider's premium behaviour is governed by
    ``OPTIONAL_ENTITLEMENT_DEFAULT_ALLOW`` (default open). Cached per-name.
    """
    resolved = (
        name or os.environ.get("OPTIONAL_ENTITLEMENT_PROVIDER") or "default"
    ).strip().lower()

    if resolved in _PROVIDERS:
        return _PROVIDERS[resolved]

    if resolved == "default":
        provider: EntitlementProvider = DefaultEntitlementProvider(
            default_allow=_env_default_allow()
        )
    else:
        raise ValueError(f"Unknown entitlement provider '{resolved}'")

    _PROVIDERS[resolved] = provider
    return provider


__all__ = [
    "DEFAULT_UPGRADE_PATH",
    "EntitlementDecision",
    "EntitlementProvider",
    "DefaultEntitlementProvider",
    "get_entitlement_provider",
]
