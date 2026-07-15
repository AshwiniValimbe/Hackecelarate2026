"""Generate synthetic lab-analyser event logs so Device Pulse can be run
immediately end-to-end. Produces events.csv and devices.csv.

    python examples/generate_sample_data.py

The fleet is 75 devices: the 7 original hand-crafted archetypes followed by
68 procedurally-generated ones. Every device carries a patient-impact
*criticality tier* (how much its failure affects patient care) and every event
carries a per-event *patient_impact* level. Both are informational only — they
are surfaced in the UI/report but do NOT change the risk score.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta

import pandas as pd

random.seed(7)

AS_OF = datetime(2026, 7, 12)
FAILURE_CODES = [
    "PIPETTE_JAM", "OPTICS_DRIFT", "TEMP_OUT_OF_RANGE", "REAGENT_LOW",
    "CALIB_FAIL", "MOTOR_STALL", "SAMPLE_CLOG", "COMM_TIMEOUT",
]
MODELS = ["Analyser-X100", "Analyser-X200", "Chem-Pro 5"]

# How critical the device is to patient care. Informational (not scored).
CRITICALITY_TIERS = ["Critical Care", "Diagnostic", "Screening", "Research"]
CRITICALITY_WEIGHTS = [0.22, 0.40, 0.28, 0.10]

# Per-event patient impact, ordered least -> most severe. Informational.
IMPACT_LEVELS = ["None", "Repeat Test", "Delayed Result", "Misdiagnosis Risk"]

PROFILES = [
    "healthy", "frequency_spike", "severity_climb",
    "emerging_pattern", "dominant_failure", "thin_history",
]
# Weights for the 68 generated devices (healthy-heavy, as in a real fleet).
PROFILE_WEIGHTS = [0.44, 0.13, 0.13, 0.12, 0.12, 0.06]

# The 7 original hand-crafted archetypes, now with a criticality tier.
# (id, model, install_years_ago, profile, criticality)
BASE_DEVICES = [
    ("LA-001", "Analyser-X100", 2.0, "healthy",          "Diagnostic"),
    ("LA-002", "Analyser-X100", 3.5, "frequency_spike",  "Critical Care"),
    ("LA-003", "Analyser-X200", 7.5, "severity_climb",   "Critical Care"),   # aging
    ("LA-004", "Analyser-X200", 1.0, "emerging_pattern", "Diagnostic"),
    ("LA-005", "Chem-Pro 5",    9.0, "dominant_failure", "Critical Care"),   # very old + failing
    ("LA-006", "Chem-Pro 5",    4.0, "healthy",          "Screening"),
    ("LA-007", "Analyser-X100", 6.5, "thin_history",     "Research"),
]


def _build_device_list():
    """7 archetypes + 68 procedurally generated devices = 75 total."""
    devices = list(BASE_DEVICES)
    for n in range(len(BASE_DEVICES) + 1, 76):  # LA-008 .. LA-075
        did = f"LA-{n:03d}"
        model = random.choice(MODELS)
        age = round(random.uniform(0.5, 12.0), 1)
        profile = random.choices(PROFILES, weights=PROFILE_WEIGHTS, k=1)[0]
        criticality = random.choices(CRITICALITY_TIERS, weights=CRITICALITY_WEIGHTS, k=1)[0]
        devices.append((did, model, age, profile, criticality))
    return devices


DEVICES = _build_device_list()


def _impact_for(sev: int, criticality: str) -> str:
    """Pick a patient-impact level from event severity, nudged by criticality.

    Higher severity -> worse impact; Critical Care devices escalate more
    readily; Research devices rarely touch patients.
    """
    if sev <= 2:
        pick = random.choice(["None", "None", "None", "Repeat Test"])
    elif sev == 3:
        pick = random.choice(["None", "Repeat Test", "Delayed Result"])
    else:  # 4-5
        pick = random.choice(["Delayed Result", "Delayed Result", "Misdiagnosis Risk"])

    idx = IMPACT_LEVELS.index(pick)
    if criticality == "Critical Care" and random.random() < 0.4:
        idx = min(idx + 1, len(IMPACT_LEVELS) - 1)
    elif criticality == "Research" and random.random() < 0.7:
        idx = 0
    return IMPACT_LEVELS[idx]


def _emit(rows, did, days_ago, code, sev, criticality):
    ts = AS_OF - timedelta(days=days_ago, hours=random.randint(0, 23))
    rows.append({"device_id": did, "timestamp": ts.isoformat(),
                 "event_code": code, "severity": sev,
                 "patient_impact": _impact_for(sev, criticality)})


def build_events():
    # Reseed so every call (e.g. each web request) yields the SAME fleet —
    # otherwise the shared random stream drifts and counts change per reload.
    random.seed(7)
    rows = []
    for did, _model, _age, profile, crit in DEVICES:
        # baseline window: days 90..360 ago ; recent window: days 0..90 ago
        if profile == "healthy":
            for _ in range(random.randint(18, 26)):
                _emit(rows, did, random.randint(91, 360), random.choice(FAILURE_CODES), random.randint(1, 3), crit)
            for _ in range(random.randint(6, 9)):
                _emit(rows, did, random.randint(0, 89), random.choice(FAILURE_CODES), random.randint(1, 3), crit)

        elif profile == "frequency_spike":
            for _ in range(random.randint(20, 28)):
                _emit(rows, did, random.randint(91, 360), random.choice(FAILURE_CODES), random.randint(1, 3), crit)
            for _ in range(random.randint(28, 36)):  # sharp rise in count
                _emit(rows, did, random.randint(0, 89), random.choice(FAILURE_CODES), random.randint(2, 3), crit)

        elif profile == "severity_climb":
            for _ in range(random.randint(20, 26)):
                _emit(rows, did, random.randint(91, 360), random.choice(FAILURE_CODES), random.randint(1, 2), crit)
            for _ in range(random.randint(8, 12)):   # similar rate, much worse severity
                _emit(rows, did, random.randint(0, 89), random.choice(FAILURE_CODES), random.randint(4, 5), crit)

        elif profile == "emerging_pattern":
            for _ in range(random.randint(18, 24)):
                _emit(rows, did, random.randint(91, 360),
                      random.choice([c for c in FAILURE_CODES if c != "OPTICS_DRIFT"]), random.randint(1, 3), crit)
            for _ in range(random.randint(5, 7)):
                _emit(rows, did, random.randint(0, 89), random.choice(FAILURE_CODES), random.randint(2, 3), crit)
            for _ in range(random.randint(4, 6)):    # new code not seen in baseline
                _emit(rows, did, random.randint(0, 89), "OPTICS_DRIFT", 3, crit)

        elif profile == "dominant_failure":
            for _ in range(random.randint(16, 22)):
                _emit(rows, did, random.randint(91, 360), random.choice(FAILURE_CODES), random.randint(1, 3), crit)
            for _ in range(random.randint(2, 3)):
                _emit(rows, did, random.randint(0, 89), random.choice(FAILURE_CODES), random.randint(2, 3), crit)
            for _ in range(random.randint(12, 16)):  # one code overwhelms recent
                _emit(rows, did, random.randint(0, 89), "MOTOR_STALL", random.randint(4, 5), crit)

        elif profile == "thin_history":
            for _ in range(2):
                _emit(rows, did, random.randint(91, 360), random.choice(FAILURE_CODES), 2, crit)
            for _ in range(2):
                _emit(rows, did, random.randint(0, 89), random.choice(FAILURE_CODES), 3, crit)

    return pd.DataFrame(rows).sort_values("timestamp")


def build_devices():
    rows = []
    for did, model, age, _profile, crit in DEVICES:
        install = AS_OF - timedelta(days=int(age * 365.25))
        rows.append({"device_id": did, "model": model,
                     "install_date": install.date().isoformat(),
                     "criticality": crit})
    return pd.DataFrame(rows)


if __name__ == "__main__":
    build_events().to_csv("events.csv", index=False)
    build_devices().to_csv("devices.csv", index=False)
    print(f"Wrote events.csv and devices.csv ({len(DEVICES)} devices)")
