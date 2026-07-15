"""Loading and normalising input data.

Two inputs:
  * events  : one row per adverse event / signal (device_id, timestamp,
              event_code, severity)
  * devices : one row per device (device_id, model, install_date)

Both can be CSV paths or already-loaded pandas DataFrames.
"""

from __future__ import annotations

from typing import Optional, Union

import pandas as pd

from .config import PulseConfig, DEFAULT_CONFIG

DataInput = Union[str, "pd.DataFrame"]

# Accepted alternative column names -> canonical name.
_EVENT_ALIASES = {
    "device_id": {"device_id", "deviceid", "serial", "serial_number", "asset_id"},
    "timestamp": {"timestamp", "event_time", "datetime", "date", "logged_at", "time"},
    "event_code": {"event_code", "code", "failure_code", "error_code", "fault_code"},
    "severity": {"severity", "sev", "severity_level", "level"},
    "patient_impact": {"patient_impact", "patient_effect", "clinical_impact", "impact"},
}
_DEVICE_ALIASES = {
    "device_id": {"device_id", "deviceid", "serial", "serial_number", "asset_id"},
    "model": {"model", "device_model", "type", "analyser_model", "analyzer_model"},
    "install_date": {"install_date", "installed", "commissioned", "install", "install_dt"},
    "criticality": {"criticality", "patient_impact_tier", "care_tier", "device_criticality"},
}

# Canonical patient-impact levels, ordered least -> most severe.
IMPACT_LEVELS = ["None", "Repeat Test", "Delayed Result", "Misdiagnosis Risk"]


def _read(data: DataInput) -> pd.DataFrame:
    if isinstance(data, pd.DataFrame):
        return data.copy()
    return pd.read_csv(data)


def _rename(df: pd.DataFrame, aliases: dict) -> pd.DataFrame:
    lower = {c.lower().strip(): c for c in df.columns}
    mapping = {}
    for canonical, options in aliases.items():
        for opt in options:
            if opt in lower:
                mapping[lower[opt]] = canonical
                break
    return df.rename(columns=mapping)


def load_events(data: DataInput, cfg: PulseConfig = DEFAULT_CONFIG) -> pd.DataFrame:
    df = _rename(_read(data), _EVENT_ALIASES)

    required = {"device_id", "timestamp"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Event data missing required columns: {sorted(missing)}")

    df["device_id"] = df["device_id"].astype(str)
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=False)
    df = df.dropna(subset=["timestamp"])

    if "event_code" not in df.columns:
        df["event_code"] = "UNSPECIFIED"
    df["event_code"] = df["event_code"].fillna("UNSPECIFIED").astype(str)

    if "severity" not in df.columns:
        df["severity"] = cfg.severity_scale_max // 2 + 1  # neutral-ish default
    df["severity"] = df["severity"].map(lambda v: _coerce_severity(v, cfg))

    # Patient impact is optional and informational; default to "None".
    if "patient_impact" not in df.columns:
        df["patient_impact"] = "None"
    df["patient_impact"] = df["patient_impact"].map(_coerce_impact)

    return df[["device_id", "timestamp", "event_code", "severity", "patient_impact"]]


def load_devices(data: Optional[DataInput]) -> Optional[pd.DataFrame]:
    if data is None:
        return None
    df = _rename(_read(data), _DEVICE_ALIASES)
    if "device_id" not in df.columns:
        raise ValueError("Device data must contain a device_id column.")
    df["device_id"] = df["device_id"].astype(str)
    if "model" not in df.columns:
        df["model"] = None
    if "install_date" in df.columns:
        df["install_date"] = pd.to_datetime(df["install_date"], errors="coerce")
    else:
        df["install_date"] = pd.NaT
    if "criticality" not in df.columns:
        df["criticality"] = None
    return df[["device_id", "model", "install_date", "criticality"]]


_IMPACT_ALIASES = {
    "none": "None", "nil": "None", "no impact": "None", "": "None",
    "repeat test": "Repeat Test", "repeat": "Repeat Test", "rerun": "Repeat Test",
    "delayed result": "Delayed Result", "delay": "Delayed Result", "delayed": "Delayed Result",
    "misdiagnosis risk": "Misdiagnosis Risk", "misdiagnosis": "Misdiagnosis Risk",
    "wrong result": "Misdiagnosis Risk",
}


def _coerce_impact(value) -> str:
    """Normalise a patient-impact value to a canonical level (default 'None')."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "None"
    key = str(value).strip().lower()
    if not key:
        return "None"
    return _IMPACT_ALIASES.get(key, str(value).strip())


def _coerce_severity(value, cfg: PulseConfig) -> float:
    """Accept numbers or category strings; clamp to the configured scale."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return float(cfg.severity_scale_max // 2 + 1)
    try:
        num = float(value)
        return max(1.0, min(float(cfg.severity_scale_max), num))
    except (TypeError, ValueError):
        key = str(value).strip().lower()
        return float(cfg.severity_map.get(key, cfg.severity_scale_max // 2 + 1))
