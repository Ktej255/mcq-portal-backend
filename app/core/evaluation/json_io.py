"""Robust JSON extraction/repair for model output (R4.2, R4.3).

Open-source models served behind OpenAI-compatible endpoints often do NOT honor
a strict ``response_mime_type`` and may wrap their JSON in prose or markdown code
fences. :class:`JsonRepair` recovers the first valid JSON object embedded in such
output so the strict schema parsers can validate it; when nothing parseable is
present it reports a typed miss so the engine can retry/degrade (R4.4/R4.5).

Pure functions, no I/O. Subject-neutral.
"""
from __future__ import annotations

import json
from typing import Any, Dict, Optional


class JsonRepair:
    """Best-effort recovery of a JSON object from noisy model output."""

    @staticmethod
    def _strip_fences(text: str) -> str:
        t = text.strip()
        if t.startswith("```"):
            lines = t.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            t = "\n".join(lines).strip()
        return t

    @staticmethod
    def _first_balanced_object(text: str) -> Optional[str]:
        """Return the first balanced ``{...}`` substring, respecting strings."""
        start = text.find("{")
        if start == -1:
            return None
        depth = 0
        in_str = False
        escape = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]
        return None

    @classmethod
    def extract_object(cls, text: str) -> Optional[Dict[str, Any]]:
        """Extract the first valid JSON object from ``text``.

        Tolerates surrounding prose and markdown fences. Returns the parsed dict,
        or ``None`` when no JSON object can be recovered (typed miss — R4.4).
        """
        if not text or not text.strip():
            return None

        stripped = cls._strip_fences(text)

        # Fast path: the whole thing is a JSON object.
        try:
            data = json.loads(stripped)
            if isinstance(data, dict):
                return data
        except (ValueError, TypeError):
            pass

        # Fallback: locate the first balanced object and parse it.
        candidate = cls._first_balanced_object(stripped)
        if candidate is None:
            return None
        try:
            data = json.loads(candidate)
        except (ValueError, TypeError):
            return None
        return data if isinstance(data, dict) else None


__all__ = ["JsonRepair"]
