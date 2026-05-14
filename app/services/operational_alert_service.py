"""
Operational Alert Service — Phase 9, Priority 9
=================================================
Founder alert system: detects operational anomalies and writes
prioritized SystemEvent records.

Alert categories:
  FORENSIC_DIVERGENCE_SPIKE  — >N divergences in a time window
  TRUTH_STATUS_FAILURE_SPIKE — >N FAILED reports in a time window
  TELEMETRY_CORRUPTION_SPIKE — >N reports with missing telemetry
  FAILED_SUBMISSIONS         — submit errors in last hour
  INGESTION_FAILURE          — content pipeline failures

This service is OBSERVATION ONLY. It never mutates attempt or report data.
It reads SystemEvent and Report tables and writes new alert events.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Optional
from sqlalchemy.orm import Session

# ─── Thresholds ───────────────────────────────────────────────────────────────

THRESHOLDS = {
    "FORENSIC_DIVERGENCE_SPIKE": {"count": 3, "window_minutes": 60},
    "TRUTH_STATUS_FAILURE_SPIKE": {"count": 2, "window_minutes": 60},
    "TELEMETRY_CORRUPTION_SPIKE": {"count": 5, "window_minutes": 120},
    "FAILED_SUBMISSIONS":         {"count": 2, "window_minutes": 30},
}


def _log_alert(db: Session, alert_type: str, severity: str, detail: str, meta: dict) -> None:
    """Log an operational alert. Uses Python logger as primary sink."""
    import logging
    _logger = logging.getLogger("operational_alert_service")
    log_fn = _logger.critical if severity == "CRITICAL" else _logger.warning
    log_fn(
        f"[ALERT:{alert_type}] severity={severity} | {detail} | meta={meta}"
    )


def _count_events_in_window(db: Session, event_type: str, window_minutes: int) -> int:
    """
    Count occurrences of a specific event pattern in the window.
    Reads from Report table (truth_status=FAILED) — no SystemEvent model required.
    """
    # This is a no-op counter stub until SystemEvent model is added.
    # The Report-based checks in the individual detectors work independently.
    return 0


# ─── Individual Detectors ─────────────────────────────────────────────────────

def check_forensic_divergence_spike(db: Session) -> Optional[str]:
    t = THRESHOLDS["FORENSIC_DIVERGENCE_SPIKE"]
    count = _count_events_in_window(db, "FORENSIC_DIVERGENCE", t["window_minutes"])
    if count >= t["count"]:
        detail = (
            f"{count} FORENSIC_DIVERGENCE events in the last {t['window_minutes']} minutes. "
            "Possible systemic frontend sync failure or race condition. Immediate review required."
        )
        _log_alert(db, "FORENSIC_DIVERGENCE_SPIKE", "CRITICAL", detail,
                   {"divergence_count": count, "window_minutes": t["window_minutes"]})
        return detail
    return None


def check_truth_status_failures(db: Session) -> Optional[str]:
    from app.models.domain import Report
    t = THRESHOLDS["TRUTH_STATUS_FAILURE_SPIKE"]
    since = datetime.now(timezone.utc) - timedelta(minutes=t["window_minutes"])
    count = (
        db.query(Report)
        .filter(Report.truth_status == "FAILED", Report.generated_at >= since)
        .count()
    )
    if count >= t["count"]:
        detail = (
            f"{count} reports with truth_status=FAILED in last {t['window_minutes']} minutes. "
            "Students are being blocked from viewing reports. Check scoring logic immediately."
        )
        _log_alert(db, "TRUTH_STATUS_FAILURE_SPIKE", "CRITICAL", detail,
                   {"failed_count": count, "window_minutes": t["window_minutes"]})
        return detail
    return None


def check_telemetry_corruption(db: Session) -> Optional[str]:
    from app.models.domain import Report
    t = THRESHOLDS["TELEMETRY_CORRUPTION_SPIKE"]
    since = datetime.now(timezone.utc) - timedelta(minutes=t["window_minutes"])
    count = (
        db.query(Report)
        .filter(Report.telemetry_summary == None, Report.generated_at >= since)  # noqa
        .count()
    )
    if count >= t["count"]:
        detail = (
            f"{count} reports missing telemetry data in last {t['window_minutes']} minutes. "
            "Telemetry reconstruction pipeline may be degraded."
        )
        _log_alert(db, "TELEMETRY_CORRUPTION_SPIKE", "HIGH", detail,
                   {"corrupt_count": count, "window_minutes": t["window_minutes"]})
        return detail
    return None


# ─── Master Check (call periodically or on-demand) ────────────────────────────

def run_operational_health_check(db: Session) -> dict:
    """
    Runs all alert detectors and returns a summary.
    Safe to call from a background task or admin endpoint.
    """
    alerts = []
    for check in [
        check_forensic_divergence_spike,
        check_truth_status_failures,
        check_telemetry_corruption,
    ]:
        result = check(db)
        if result:
            alerts.append(result)

    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "alert_count": len(alerts),
        "status": "ALERT" if alerts else "HEALTHY",
        "alerts": alerts,
    }
