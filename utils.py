"""Utility functions for FermentGuard: calculations, alerts, simulation, and helpers."""

from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple, Optional
import random
import math
import pandas as pd


# =============================================================================
# OPTIMAL RANGES (tunable for honey vinegar submerged generator)
# =============================================================================
OPTIMAL_RANGES = {
    "pH": {"min": 3.2, "max": 4.2, "target": 3.6, "unit": "", "label": "pH"},
    "temperature_C": {"min": 24.0, "max": 30.0, "target": 27.0, "unit": "°C", "label": "Temperature"},
    "dissolved_oxygen": {"min": 25.0, "max": 65.0, "target": 45.0, "unit": "%", "label": "Dissolved Oxygen"},
    "aeration_rate": {"min": 0.3, "max": 1.8, "target": 0.9, "unit": "L/min", "label": "Aeration"},
}


def get_status_color(value: float, param: str) -> str:
    """Return 'good', 'warn', or 'bad' based on optimal ranges."""
    if param not in OPTIMAL_RANGES:
        return "good"
    r = OPTIMAL_RANGES[param]
    if r["min"] <= value <= r["max"]:
        return "good"
    # Allow slight buffer for warnings
    buffer = (r["max"] - r["min"]) * 0.15
    if (r["min"] - buffer) <= value <= (r["max"] + buffer):
        return "warn"
    return "bad"


def check_reading_alerts(reading: Dict[str, Any]) -> List[Dict[str, str]]:
    """Generate human-friendly alerts/warnings for a single reading dict."""
    alerts: List[Dict[str, str]] = []
    if not reading:
        return alerts

    # pH
    ph = reading.get("pH")
    if ph is not None:
        status = get_status_color(ph, "pH")
        if status == "bad":
            if ph < OPTIMAL_RANGES["pH"]["min"]:
                alerts.append({"level": "warning", "msg": f"pH {ph:.2f} is quite low — monitor for over-acidification."})
            else:
                alerts.append({"level": "info", "msg": f"pH {ph:.2f} is high — fermentation may be slow or stalled."})
        elif status == "warn":
            alerts.append({"level": "info", "msg": f"pH {ph:.2f} near edge of optimal band (3.2–4.2)."})

    # Temperature
    temp = reading.get("temperature_C")
    if temp is not None:
        status = get_status_color(temp, "temperature_C")
        if status == "bad":
            if temp < 24:
                alerts.append({"level": "warning", "msg": f"Temperature {temp:.1f}°C too cold — acetobacter activity slowed."})
            else:
                alerts.append({"level": "warning", "msg": f"Temperature {temp:.1f}°C too warm — risk of off-flavors or die-off."})
        elif status == "warn":
            alerts.append({"level": "info", "msg": f"Temperature {temp:.1f}°C near limits (ideal 24–30°C)."})

    # Dissolved Oxygen
    do_val = reading.get("dissolved_oxygen")
    if do_val is not None:
        status = get_status_color(do_val, "dissolved_oxygen")
        if status == "bad":
            if do_val < 25:
                alerts.append({"level": "warning", "msg": f"DO {do_val:.0f}% low — increase aeration or check stone diffuser."})
            else:
                alerts.append({"level": "info", "msg": f"DO {do_val:.0f}% high — can usually reduce aeration now."})
        elif status == "warn" and do_val > 65:
            alerts.append({"level": "info", "msg": f"DO {do_val:.0f}% — consider lowering aeration to save energy."})

    # Aeration rate (less critical)
    aer = reading.get("aeration_rate")
    if aer is not None and aer > 2.0:
        alerts.append({"level": "info", "msg": f"Aeration {aer:.1f} L/min is quite high for small batches."})

    return alerts


def estimate_acidity_progress(df: pd.DataFrame, target_ph: float = 3.5) -> Dict[str, Any]:
    """
    Estimate fermentation progress based on pH trajectory.
    Returns dict with progress_percent, days_elapsed, trend, and interpretation.
    """
    if df.empty or "pH" not in df.columns or df["pH"].isna().all():
        return {"progress_percent": 0.0, "interpretation": "No pH data yet."}

    ph_series = df["pH"].dropna()
    if len(ph_series) < 1:
        return {"progress_percent": 0.0, "interpretation": "Insufficient data."}

    start_ph = ph_series.iloc[0]
    current_ph = ph_series.iloc[-1]

    # Rough model: pH drop from ~4.8–5.0 down toward 3.3–3.5 is ~80-90% of journey for good vinegar
    # We treat 5.0 -> 3.5 as 100% reference scale
    reference_drop = 5.0 - target_ph
    actual_drop = start_ph - current_ph
    progress = max(0.0, min(100.0, (actual_drop / reference_drop) * 100))

    # Time based
    if "measured_at" in df.columns:
        times = pd.to_datetime(df["measured_at"])
        days_elapsed = max(1, (times.iloc[-1] - times.iloc[0]).days)
    else:
        days_elapsed = 1

    # Simple trend
    if len(ph_series) >= 3:
        recent = ph_series.tail(3)
        slope = (recent.iloc[-1] - recent.iloc[0]) / 2
        if slope < -0.03:
            trend = "dropping steadily (good)"
        elif slope > 0.02:
            trend = "rising (check aeration/oxygen)"
        else:
            trend = "stable"
    else:
        trend = "limited readings"

    interp = f"{progress:.0f}% toward target acidity. Trend: {trend}. ~{days_elapsed} days of data."

    return {
        "progress_percent": round(progress, 1),
        "current_ph": round(current_ph, 2),
        "start_ph": round(start_ph, 2),
        "days_elapsed": int(days_elapsed),
        "trend": trend,
        "interpretation": interp,
    }


def generate_simulation_batch(
    batch_id: str,
    start_date: str,
    num_days: int = 8,
    readings_per_day: int = 1
) -> List[Dict[str, Any]]:
    """
    Generate realistic simulated measurement data for a honey vinegar batch.
    Returns list of dicts ready for add_measurement.
    """
    random.seed(hash(batch_id) % 2**32)  # reproducible per batch

    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    logs: List[Dict[str, Any]] = []

    # Start conditions for submerged honey vinegar
    current_ph = 4.90 + random.uniform(-0.08, 0.08)
    current_temp = 26.8 + random.uniform(-0.6, 0.6)
    current_do = 32.0 + random.uniform(-4, 5)
    current_aer = 0.85 + random.uniform(-0.15, 0.25)

    for day in range(num_days + 1):
        # Daily drift model (acetobacter consumes ethanol -> acid, pH falls, temp stable with daily cycle)
        ph_drop = random.uniform(0.035, 0.085) * (1.0 - (day / (num_days + 3)))  # slows as it acidifies
        current_ph = max(3.35, current_ph - ph_drop)

        # Temperature: gentle diurnal variation + small random walk
        temp_drift = random.gauss(0, 0.35)
        current_temp = 26.5 + 0.8 * math.sin(day * 1.1) + temp_drift
        current_temp = max(23.5, min(29.8, current_temp))

        # DO responds to aeration + biological consumption (rises early, then falls slightly)
        do_drift = random.gauss(0, 3.5)
        current_do = current_do + do_drift - (day * 0.6)
        current_do = max(18.0, min(78.0, current_do))

        # Aeration slowly tapers as batch matures
        aer_drift = random.gauss(0, 0.06)
        current_aer = max(0.35, min(1.6, current_aer + aer_drift - 0.025 * day))

        measured_at = (start_dt + timedelta(days=day, hours=random.randint(8, 18))).strftime("%Y-%m-%d %H:%M")

        notes_options = [
            "Routine check.",
            "Smell developing nicely.",
            "Mother visible and healthy.",
            "Slight foam, good gas exchange.",
            "Sampled — clean sharp acidity.",
            "Adjusted stone position slightly.",
            "Very consistent bubbles today.",
            "Temp stable overnight.",
        ]
        notes = random.choice(notes_options) if random.random() > 0.25 else ""

        logs.append({
            "batch_id": batch_id,
            "measured_at": measured_at,
            "pH": round(current_ph, 2),
            "dissolved_oxygen": round(current_do, 1),
            "temperature_C": round(current_temp, 1),
            "aeration_rate": round(current_aer, 2),
            "notes": notes,
        })

    return logs


def format_timestamp(ts: Any) -> str:
    """Pretty print timestamps for UI."""
    if pd.isna(ts):
        return "—"
    if isinstance(ts, str):
        try:
            dt = datetime.fromisoformat(ts.replace("Z", ""))
        except Exception:
            return str(ts)[:16]
        return dt.strftime("%Y-%m-%d %H:%M")
    if isinstance(ts, (datetime, pd.Timestamp)):
        return ts.strftime("%Y-%m-%d %H:%M")
    return str(ts)


def df_to_csv_bytes(df: pd.DataFrame) -> bytes:
    """Return CSV bytes suitable for st.download_button."""
    if df.empty:
        return b""
    # Make measured_at human friendly on export
    out = df.copy()
    if "measured_at" in out.columns:
        out["measured_at"] = pd.to_datetime(out["measured_at"]).dt.strftime("%Y-%m-%d %H:%M:%S")
    return out.to_csv(index=False).encode("utf-8")
