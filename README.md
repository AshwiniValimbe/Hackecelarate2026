# Device Pulse

**Predictive maintenance intelligence for medical devices** — starting with lab
analysers, built for fleet management at healthcare organisations and device
manufacturers.

Device Pulse reads each device's recent adverse-event / signal log (default
**90 days**) against its **9-month historical baseline** and computes three
signals, an **age-adjusted risk score**, and a **fleet-ranked maintenance
priority** with plain-English reasons.

## The three signals

| Signal | What it measures | Labels |
|--------|------------------|--------|
| **Frequency** | Recent event rate vs historical rate | Normal · Elevated · High · Critical |
| **Severity** | Average severity of recent vs historical events | Stable · Worsening · Escalating |
| **Pattern** | Concentration of the dominant failure code in recent events | Distributed · Emerging · Concentrated · Dominant |

**Device age** is a first-class input: devices older than 6 years receive an
age-risk multiplier (banded: >6yr ×1.15, >8yr ×1.30, >10yr ×1.50) applied to
the overall score, and ≥8yr devices are flagged for end-of-life watch.

Each device rolls up to a **risk score (0–100)** and a **status**:
`Healthy · Watch · At Risk · Critical`, with a recommended action.

## Patient impact (informational)

Two patient-facing dimensions are surfaced alongside the score but **do not
change it** — they add clinical context for triage:

- **Device criticality** — a per-device care tier (`Critical Care · Diagnostic ·
  Screening · Research`) describing how much a failure affects patient care.
- **Per-event patient impact** — each event carries an impact level
  (`None · Repeat Test · Delayed Result · Misdiagnosis Risk`); the recent window
  rolls up to a worst-level and a count of clinically-impactful events.

## Install

```bash
pip install -r requirements.txt      # or: pip install -e .
```

## Quick start

```bash
# 1. Generate synthetic sample data (75-device lab-analyser fleet)
cd examples && python generate_sample_data.py && cd ..

# 2. Run the fleet analysis
python -m device_pulse.cli --events examples/events.csv \
                           --devices examples/devices.csv \
                           --as-of 2026-07-12 \
                           --output report.csv
```

Show only devices needing attention, and export full detail:

```bash
python -m device_pulse.cli --events examples/events.csv --devices examples/devices.csv \
    --min-status Watch --json report.json
```

## Use as a library

```python
from device_pulse import DevicePulse

pulse = DevicePulse()
assessments = pulse.assess_fleet("events.csv", "devices.csv", as_of="2026-07-12")

for a in assessments:                 # already sorted by risk, highest first
    print(a.device_id, a.status, a.risk_score, a.frequency.label,
          a.severity.label, a.pattern.label)

report_df = pulse.fleet_report(assessments)   # tidy pandas DataFrame
```

## Input format

**events.csv** (one row per event; column names are auto-detected from common aliases):

| device_id | timestamp | event_code | severity | patient_impact |
|-----------|-----------|------------|----------|----------------|
| LA-001 | 2026-05-01T09:12:00 | PIPETTE_JAM | 3 | Delayed Result |

`severity` accepts a number (1–5) or a category (`minor`, `major`, `critical`, …).
`patient_impact` is optional (`None · Repeat Test · Delayed Result · Misdiagnosis
Risk`); defaults to `None` when absent.

**devices.csv** (optional; enables age analysis):

| device_id | model | install_date | criticality |
|-----------|-------|--------------|-------------|
| LA-001 | Analyser-X100 | 2024-07-01 | Critical Care |

`criticality` is optional (`Critical Care · Diagnostic · Screening · Research`).

## Tuning

Every threshold lives in `device_pulse/config.py` (`PulseConfig`). Pass a
customised config into `DevicePulse(config=...)` — no algorithm changes needed.

## Tests

```bash
pytest tests/ -q
```

## Design notes

- Signal functions in `signals.py` are pure (no I/O, no clock) so they are easy
  to test and audit — important for a regulated context.
- Devices with thin history (below the configured minimum event counts) have
  their score damped so the tool does not raise alarms on noise.
- The tool is decision-support: it surfaces and ranks risk with explanations;
  it does not auto-action devices.
