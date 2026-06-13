"""
prediction.py — Predictive Failure Engine for ConfidenceOS V2 (Module 7).

Forecasts when each sensor will cross confidence tier thresholds.
Uses numpy polyfit for linear regression — no scikit-learn dependency.
"""

import numpy as np
from datetime import datetime, timedelta


# Tier thresholds
THRESHOLD_LOW = 50.0
THRESHOLD_CRITICAL = 20.0


def predict_sensor(confidence_history: list[dict]) -> dict:
    """
    Predict when a sensor's confidence will cross LOW and CRITICAL thresholds.
    
    Args:
        confidence_history: list of dicts with 'confidence_pct' and 'timestamp' keys,
                           ordered by timestamp ascending.
    
    Returns:
        Prediction dict with time-to-threshold forecasts.
    """
    if len(confidence_history) < 10:
        return {
            "model_type": "insufficient_data",
            "model_fit": "insufficient",
            "time_to_low_hours": None,
            "time_to_critical_hours": None,
            "range_low": None,
            "range_critical": None,
            "primary_driver": None,
            "driver_rate": None,
            "recommended_action": "Insufficient data for prediction. Need at least 10 data points.",
        }

    # Extract timestamps and confidence values
    timestamps = []
    values = []
    sub_scores = {"calibration": [], "stability": [], "cross_sensor": [], "plausibility": []}

    for entry in confidence_history:
        ts = entry.get("timestamp")
        if isinstance(ts, str):
            try:
                ts = datetime.fromisoformat(ts)
            except (ValueError, TypeError):
                continue
        elif not isinstance(ts, datetime):
            continue

        timestamps.append(ts.timestamp())
        values.append(entry["confidence_pct"])

        if entry.get("calibration_score") is not None:
            sub_scores["calibration"].append(entry["calibration_score"])
        if entry.get("stability_score") is not None:
            sub_scores["stability"].append(entry["stability_score"])
        if entry.get("cross_sensor_score") is not None:
            sub_scores["cross_sensor"].append(entry["cross_sensor_score"])
        if entry.get("plausibility_score") is not None:
            sub_scores["plausibility"].append(entry["plausibility_score"])

    if len(timestamps) < 10:
        return {
            "model_type": "insufficient_data",
            "model_fit": "insufficient",
            "time_to_low_hours": None,
            "time_to_critical_hours": None,
            "range_low": None,
            "range_critical": None,
            "primary_driver": None,
            "driver_rate": None,
            "recommended_action": "Insufficient valid data points.",
        }

    t = np.array(timestamps)
    v = np.array(values)

    # Normalize timestamps to hours from start
    t_hours = (t - t[0]) / 3600.0
    current_time_hours = t_hours[-1]

    # Fit linear model: confidence = a*t + b
    try:
        coeffs = np.polyfit(t_hours, v, 1)
        slope = coeffs[0]  # %/hour
        intercept = coeffs[1]

        # R² calculation
        v_pred = np.polyval(coeffs, t_hours)
        ss_res = np.sum((v - v_pred) ** 2)
        ss_tot = np.sum((v - np.mean(v)) ** 2)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
    except Exception:
        return {
            "model_type": "error",
            "model_fit": "insufficient",
            "time_to_low_hours": None,
            "time_to_critical_hours": None,
            "range_low": None,
            "range_critical": None,
            "primary_driver": None,
            "driver_rate": None,
            "recommended_action": "Model fitting failed.",
        }

    # Determine model quality
    if r_squared >= 0.85:
        model_fit = "good"
    elif r_squared >= 0.7:
        model_fit = "fair"
    else:
        model_fit = "poor"

    current_confidence = v[-1]
    model_type = "linear"

    # Step-change detection: recent confidence dropped sharply versus prior window.
    if len(v) >= 12:
        recent_avg = float(np.mean(v[-4:]))
        previous_avg = float(np.mean(v[-12:-4]))
        if previous_avg - recent_avg >= 12:
            model_type = "step_change"
            model_fit = "good"

    # Exponential-like degradation: log(confidence) fits better than linear.
    if np.all(v > 0) and model_type == "linear":
        try:
            exp_coeffs = np.polyfit(t_hours, np.log(v), 1)
            exp_pred = np.exp(np.polyval(exp_coeffs, t_hours))
            exp_res = np.sum((v - exp_pred) ** 2)
            if exp_res < ss_res * 0.85 and exp_coeffs[0] < 0:
                model_type = "exponential"
                slope = exp_coeffs[0] * current_confidence
                model_fit = "good" if r_squared >= 0.75 else "fair"
        except Exception:
            pass

    # Predict time to thresholds (only if slope is negative — degrading)
    time_to_low = None
    time_to_critical = None
    range_low = None
    range_critical = None

    if slope < -0.01:  # Meaningful negative slope
        # Time from NOW to threshold crossing
        if current_confidence > THRESHOLD_LOW:
            t_low = (THRESHOLD_LOW - intercept) / slope  # absolute hours from start
            hours_from_now = t_low - current_time_hours
            if hours_from_now > 0:
                time_to_low = round(hours_from_now, 1)
                # Confidence interval based on residual std
                residual_std = np.std(v - v_pred) if len(v) > 2 else 0
                if residual_std > 0 and slope != 0:
                    t_uncertainty = abs(residual_std / slope)
                    range_low = [
                        round(max(0, hours_from_now - t_uncertainty), 1),
                        round(hours_from_now + t_uncertainty, 1),
                    ]

        if current_confidence > THRESHOLD_CRITICAL:
            t_crit = (THRESHOLD_CRITICAL - intercept) / slope
            hours_from_now = t_crit - current_time_hours
            if hours_from_now > 0:
                time_to_critical = round(hours_from_now, 1)
                residual_std = np.std(v - v_pred) if len(v) > 2 else 0
                if residual_std > 0 and slope != 0:
                    t_uncertainty = abs(residual_std / slope)
                    range_critical = [
                        round(max(0, hours_from_now - t_uncertainty), 1),
                        round(hours_from_now + t_uncertainty, 1),
                    ]

    # Find primary degradation driver (which sub-score is declining fastest)
    primary_driver = None
    driver_rate = None
    if len(t_hours) > 5:
        for score_name, score_vals in sub_scores.items():
            if len(score_vals) >= 5:
                sv = np.array(score_vals[-len(t_hours):]) if len(score_vals) >= len(t_hours) else np.array(score_vals)
                th = t_hours[-len(sv):]
                try:
                    sc = np.polyfit(th, sv * 100, 1)  # Convert to %
                    if primary_driver is None or sc[0] < driver_rate:
                        primary_driver = score_name
                        driver_rate = round(sc[0], 2)
                except Exception:
                    pass

    # Generate recommended action
    recommended_action = _generate_action(
        current_confidence, time_to_low, time_to_critical, primary_driver
    )

    return {
        "model_type": model_type,
        "model_fit": model_fit,
        "slope_per_hour": round(slope, 3),
        "r_squared": round(r_squared, 3),
        "time_to_low_hours": time_to_low,
        "time_to_critical_hours": time_to_critical,
        "range_low": range_low,
        "range_critical": range_critical,
        "confidence_interval": range_critical or range_low,
        "primary_driver": primary_driver,
        "driver_rate": driver_rate,
        "recommended_action": recommended_action,
        "action": recommended_action,
    }


def _generate_action(confidence, time_to_low, time_to_critical, driver):
    """Generate a plain-English recommended action."""
    if confidence <= THRESHOLD_CRITICAL:
        return "URGENT: Sensor is at CRITICAL confidence. Manual verification required immediately."
    
    if time_to_critical is not None and time_to_critical < 4:
        driver_text = f" ({driver} declining)" if driver else ""
        return f"Schedule calibration within {time_to_critical:.0f} hours{driver_text}. Do not use for safety decisions without manual verification."
    
    if time_to_low is not None and time_to_low < 8:
        return f"Monitor closely. Confidence predicted to reach LOW tier in ~{time_to_low:.0f} hours. Consider scheduling maintenance."
    
    if time_to_low is not None:
        return f"Stable degradation trend. LOW tier expected in ~{time_to_low:.0f} hours. Normal maintenance scheduling."
    
    return "No significant degradation trend detected. Sensor operating normally."


def predict_all_sensors(confidence_histories: dict[str, list[dict]]) -> dict[str, dict]:
    """
    Run predictions for all sensors.
    
    Args:
        confidence_histories: {sensor_id: [confidence_history_entries]}
    
    Returns:
        {sensor_id: prediction_dict}
    """
    predictions = {}
    for sensor_id, history in confidence_histories.items():
        pred = predict_sensor(history)
        pred["sensor_id"] = sensor_id
        # Add current confidence from latest entry
        if history:
            pred["current_confidence"] = history[-1].get("confidence_pct", 0)
            pred["current_tier"] = history[-1].get("tier", "HIGH")
        predictions[sensor_id] = pred
    return predictions
