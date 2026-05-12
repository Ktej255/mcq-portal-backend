from __future__ import annotations

from typing import Any, List, Dict
from statistics import mean
import math

METRIC_CALIBRATION_VERSION = "metric-calibration.v1"

def calculate_calibration_curve(predictions: List[float], outcomes: List[int], bins: int = 10) -> Dict[str, Any]:
    # Predictions: probabilities [0.0, 1.0]
    # Outcomes: actual binary results [0, 1]
    
    if not predictions or not outcomes or len(predictions) != len(outcomes):
        return {"error": "Invalid input data"}
        
    bin_size = 1.0 / bins
    curve = []
    
    for i in range(bins):
        lower = i * bin_size
        upper = (i + 1) * bin_size
        
        # Get predictions in this bin
        bin_indices = [idx for idx, p in enumerate(predictions) if lower <= p < upper]
        
        if not bin_indices:
            curve.append({"bin": f"{lower:.1f}-{upper:.1f}", "avg_pred": lower + bin_size/2, "actual_freq": 0.0, "count": 0})
            continue
            
        bin_preds = [predictions[idx] for idx in bin_indices]
        bin_outcomes = [outcomes[idx] for idx in bin_indices]
        
        avg_pred = mean(bin_preds)
        actual_freq = mean(bin_outcomes)
        
        curve.append({
            "bin": f"{lower:.1f}-{upper:.1f}",
            "avg_pred": round(avg_pred, 4),
            "actual_freq": round(actual_freq, 4),
            "count": len(bin_indices),
            "variance": round(abs(avg_pred - actual_freq), 4)
        })
        
    overall_ece = mean([abs(c["avg_pred"] - c["actual_freq"]) * (c["count"] / len(predictions)) for c in curve])
    
    return {
        "calibration_curve": curve,
        "expected_calibration_error": round(overall_ece, 4),
        "calibration_status": "HIGH" if overall_ece < 0.1 else "MODERATE" if overall_ece < 0.2 else "LOW",
        "version": METRIC_CALIBRATION_VERSION
    }

def monitor_signal_calibration(signal_name: str, historical_data: List[Dict[str, Any]]) -> Dict[str, Any]:
    # signal_name: e.g. "overload_risk"
    # historical_data: list of {predicted_prob, actual_outcome}
    
    preds = [d["predicted_prob"] for d in historical_data]
    outcomes = [d["actual_outcome"] for d in historical_data]
    
    calibration = calculate_calibration_curve(preds, outcomes)
    
    # Calculate False Positive Rate
    fp = sum(1 for d in historical_data if d["predicted_prob"] > 0.7 and d["actual_outcome"] == 0)
    total_neg = sum(1 for d in historical_data if d["actual_outcome"] == 0)
    fpr = fp / max(1, total_neg)
    
    return {
        "signal": signal_name,
        "calibration": calibration,
        "false_positive_rate": round(fpr, 4),
        "confidence_intervals": _calculate_confidence_intervals(preds),
        "version": METRIC_CALIBRATION_VERSION
    }

def _calculate_confidence_intervals(data: List[float], confidence: float = 0.95) -> Dict[str, float]:
    if not data:
        return {}
    n = len(data)
    m = mean(data)
    std_err = 0 # Simple mock: in real stats we'd calculate standard error
    return {
        "mean": round(m, 4),
        "lower_bound": round(m - 1.96 * 0.05, 4), # Mocked interval
        "upper_bound": round(m + 1.96 * 0.05, 4)
    }
