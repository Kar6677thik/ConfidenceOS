"""
adaptive_thresholds.py - Adaptive operating envelope utilities.

Computes per-sensor learned envelopes from recent readings. The implementation
uses mean and standard deviation so it stays dependency-light for the demo while
matching the PRD behavior of learned plausibility bands.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from statistics import mean, pstdev

from database import SensorReading, AnomalyLog, AdaptiveEnvelopeLog


def compute_adaptive_envelopes(db, plant_id: str, hours: float = 72.0) -> dict:
    """Compute and persist learned envelopes for a plant."""
    cutoff = datetime.utcnow() - timedelta(hours=hours)

    # Exclude only sensor_fault anomalies from envelope computation.
    # process_abnormality events (mass-balance flags) are real process data and
    # should NOT be excluded — they are valid operating points for envelope learning.
    # Excluding them would allow the envelope to drift toward abnormal conditions.
    sensor_fault_types = {"confidence_low", "confidence_critical", "stale_reading"}
    anomaly_sensor_ids = {
        row.sensor_id
        for row in db.query(AnomalyLog)
        .filter(
            AnomalyLog.plant_id == plant_id,
            AnomalyLog.timestamp >= cutoff,
            AnomalyLog.anomaly_type.in_(list(sensor_fault_types)),
        )
        .all()
    }

    readings = (
        db.query(SensorReading)
        .filter(SensorReading.plant_id == plant_id, SensorReading.timestamp >= cutoff)
        .order_by(SensorReading.timestamp.asc())
        .all()
    )

    grouped: dict[str, dict] = {}
    for reading in readings:
        if reading.sensor_id in anomaly_sensor_ids:
            continue
        bucket = grouped.setdefault(
            reading.sensor_id,
            {"sensor_type": reading.sensor_type, "values": []},
        )
        bucket["values"].append(reading.value)

    envelopes = {}
    for sensor_id, data in grouped.items():
        values = data["values"]
        if len(values) < 10:
            continue

        avg = mean(values)
        std = pstdev(values) or max(abs(avg) * 0.02, 0.1)
        normal_min = avg - 3 * std
        normal_max = avg + 3 * std

        entry = AdaptiveEnvelopeLog(
            plant_id=plant_id,
            sensor_id=sensor_id,
            sensor_type=data["sensor_type"],
            mean_value=avg,
            std_dev=std,
            normal_min=normal_min,
            normal_max=normal_max,
            sample_count=len(values),
        )
        db.add(entry)

        envelopes[sensor_id] = {
            "sensor_id": sensor_id,
            "sensor_type": data["sensor_type"],
            "mean": round(avg, 3),
            "std_dev": round(std, 3),
            "normal_min": round(normal_min, 3),
            "normal_max": round(normal_max, 3),
            "sample_count": len(values),
            "source": "learned",
        }

    db.commit()
    return envelopes

