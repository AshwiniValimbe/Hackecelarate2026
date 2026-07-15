"""Device Pulse engine: turns event logs into per-device and fleet read-outs."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Optional, Union

import pandas as pd

from .config import PulseConfig, DEFAULT_CONFIG
from .loaders import load_events, load_devices
from .models import DeviceAssessment, SignalResult
from .signals import compute_frequency, compute_severity, compute_pattern


class DevicePulse:
    def __init__(self, config: PulseConfig = DEFAULT_CONFIG):
        self.cfg = config

    # ---------------------------------------------------------------- fleet
    def assess_fleet(
        self,
        events: Union[str, pd.DataFrame],
        devices: Optional[Union[str, pd.DataFrame]] = None,
        as_of: Optional[Union[str, datetime]] = None,
    ) -> List[DeviceAssessment]:
        ev = load_events(events, self.cfg)
        dev = load_devices(devices)
        as_of_dt = self._resolve_as_of(as_of, ev)

        device_ids = set(ev["device_id"].unique())
        if dev is not None:
            device_ids |= set(dev["device_id"].unique())

        model_lookup, install_lookup, crit_lookup = {}, {}, {}
        if dev is not None:
            model_lookup = dict(zip(dev["device_id"], dev["model"]))
            install_lookup = dict(zip(dev["device_id"], dev["install_date"]))
            crit_lookup = dict(zip(dev["device_id"], dev["criticality"]))

        results = []
        for did in sorted(device_ids):
            device_events = ev[ev["device_id"] == did]
            results.append(
                self._assess_one(
                    device_id=did,
                    device_events=device_events,
                    model=model_lookup.get(did),
                    install_date=install_lookup.get(did),
                    criticality=crit_lookup.get(did),
                    as_of_dt=as_of_dt,
                )
            )
        results.sort(key=lambda a: a.risk_score, reverse=True)
        return results

    def fleet_report(self, assessments: List[DeviceAssessment]) -> pd.DataFrame:
        return pd.DataFrame([a.summary_row() for a in assessments])

    def recent_events(
        self,
        events: Union[str, pd.DataFrame],
        device_id: str,
        as_of: Optional[Union[str, datetime]] = None,
    ) -> pd.DataFrame:
        """Return one device's events within the recent window, newest first.

        Uses the same loader + windowing as the assessment so the two stay
        consistent (same as_of, same recent_window_days).
        """
        ev = load_events(events, self.cfg)
        as_of_dt = self._resolve_as_of(as_of, ev)
        recent_start = as_of_dt - timedelta(days=self.cfg.recent_window_days)
        sub = ev[
            (ev["device_id"] == str(device_id))
            & (ev["timestamp"] > recent_start)
            & (ev["timestamp"] <= as_of_dt)
        ]
        return sub.sort_values("timestamp", ascending=False)

    # --------------------------------------------------------------- device
    def _assess_one(
        self,
        device_id: str,
        device_events: pd.DataFrame,
        model,
        install_date,
        criticality,
        as_of_dt: datetime,
    ) -> DeviceAssessment:
        cfg = self.cfg
        recent_start = as_of_dt - timedelta(days=cfg.recent_window_days)
        baseline_start = recent_start - timedelta(days=cfg.baseline_window_days)

        recent = device_events[
            (device_events["timestamp"] > recent_start)
            & (device_events["timestamp"] <= as_of_dt)
        ]
        baseline = device_events[
            (device_events["timestamp"] > baseline_start)
            & (device_events["timestamp"] <= recent_start)
        ]

        recent_count = len(recent)
        baseline_count = len(baseline)
        data_sufficient = (
            recent_count >= cfg.min_recent_events
            and baseline_count >= cfg.min_baseline_events
        )

        frequency = compute_frequency(recent_count, baseline_count, cfg)
        severity = compute_severity(
            recent["severity"].tolist(), baseline["severity"].tolist(), cfg
        )
        pattern = compute_pattern(
            recent["event_code"].tolist(), baseline["event_code"].tolist(), cfg
        )

        age_years = self._age_years(install_date, as_of_dt)
        age_factor = self._age_factor(age_years)
        eol_watch = age_years is not None and age_years >= cfg.end_of_life_watch_years

        risk_score = self._risk_score(frequency, severity, pattern, age_factor)
        # Insufficient data -> damp the score so we don't cry wolf on thin history.
        if not data_sufficient:
            risk_score = min(risk_score, cfg.status_at_risk_min - 0.1)

        status = self._status(risk_score)
        # Patient impact is informational only — computed here but never fed
        # into risk_score above.
        patient_impact = self._patient_impact_rollup(recent.get("patient_impact"))
        criticality = None if criticality is None or pd.isna(criticality) else str(criticality)
        reasons = self._reasons(
            frequency, severity, pattern, age_years, age_factor, eol_watch, data_sufficient
        )
        action = self._recommended_action(status, eol_watch)

        return DeviceAssessment(
            device_id=device_id,
            model=model,
            as_of=as_of_dt.date().isoformat(),
            age_years=age_years,
            age_factor=age_factor,
            end_of_life_watch=eol_watch,
            recent_event_count=recent_count,
            baseline_event_count=baseline_count,
            data_sufficient=data_sufficient,
            frequency=frequency,
            severity=severity,
            pattern=pattern,
            risk_score=risk_score,
            status=status,
            recommended_action=action,
            reasons=reasons,
            criticality=criticality,
            patient_impact=patient_impact,
        )

    # ------------------------------------------------------------- scoring
    def _risk_score(
        self,
        frequency: SignalResult,
        severity: SignalResult,
        pattern: SignalResult,
        age_factor: float,
    ) -> float:
        cfg = self.cfg
        raw = (
            frequency.points * cfg.weight_frequency
            + severity.points * cfg.weight_severity
            + pattern.points * cfg.weight_pattern
        )
        raw_max = (
            3.0 * cfg.weight_frequency
            + 2.0 * cfg.weight_severity
            + 3.0 * cfg.weight_pattern
        )
        base = raw / raw_max if raw_max else 0.0
        return min(100.0, base * 100.0 * age_factor)

    # ------------------------------------------------------- patient impact
    def _patient_impact_rollup(self, impact_values) -> dict:
        """Summarise recent-window patient impact. Informational only.

        Returns per-level counts, the worst level present, and the number of
        "elevated" events (Delayed Result or worse).
        """
        from .loaders import IMPACT_LEVELS

        counts = {lvl: 0 for lvl in IMPACT_LEVELS}
        if impact_values is not None:
            for v in impact_values:
                counts[v] = counts.get(v, 0) + 1

        worst = "None"
        for lvl in IMPACT_LEVELS:
            if counts.get(lvl, 0) > 0:
                worst = lvl
        elevated = counts.get("Delayed Result", 0) + counts.get("Misdiagnosis Risk", 0)
        total = sum(counts.values())
        return {
            "counts": counts,
            "worst": worst,
            "elevated_count": elevated,
            "total": total,
        }

    def _status(self, score: float) -> str:
        cfg = self.cfg
        if score >= cfg.status_critical_min:
            return "Critical"
        if score >= cfg.status_at_risk_min:
            return "At Risk"
        if score >= cfg.status_watch_min:
            return "Watch"
        return "Healthy"

    # ----------------------------------------------------------------- age
    def _age_years(self, install_date, as_of_dt: datetime) -> Optional[float]:
        if install_date is None or pd.isna(install_date):
            return None
        install = pd.to_datetime(install_date)
        return max(0.0, (as_of_dt - install.to_pydatetime()).days / 365.25)

    def _age_factor(self, age_years: Optional[float]) -> float:
        if age_years is None:
            return 1.0
        for upper, factor in self.cfg.age_factor_bands:
            if age_years <= upper:
                return factor
        return self.cfg.age_factor_bands[-1][1]

    # ------------------------------------------------------------- narrate
    def _reasons(
        self, frequency, severity, pattern, age_years, age_factor, eol_watch, data_sufficient
    ) -> List[str]:
        reasons = []
        if frequency.label != "Normal":
            reasons.append(f"Frequency {frequency.label}: {frequency.explanation}")
        if severity.label != "Stable":
            reasons.append(f"Severity {severity.label}: {severity.explanation}")
        if pattern.label not in ("Distributed",):
            reasons.append(f"Pattern {pattern.label}: {pattern.explanation}")
        if age_factor > 1.0 and age_years is not None:
            reasons.append(
                f"Device is {age_years:.1f} yrs old (>{self.cfg.age_threshold_years} yr), "
                f"age risk x{age_factor}."
            )
        if eol_watch:
            reasons.append("End-of-life watch: plan replacement / enhanced monitoring.")
        if not data_sufficient:
            reasons.append("Limited history: score damped until more data accrues.")
        if not reasons:
            reasons.append("All signals within normal range.")
        return reasons

    def _recommended_action(self, status: str, eol_watch: bool) -> str:
        base = {
            "Critical": "Dispatch service / take out of rotation; review before next run.",
            "At Risk": "Schedule preventive maintenance within the maintenance window.",
            "Watch": "Increase monitoring cadence; review at next fleet check.",
            "Healthy": "No action; continue routine monitoring.",
        }[status]
        if eol_watch and status in ("Watch", "At Risk", "Critical"):
            base += " Consider replacement planning (aging asset)."
        return base

    # ---------------------------------------------------------------- util
    def _resolve_as_of(self, as_of, events: pd.DataFrame) -> datetime:
        if as_of is None:
            return events["timestamp"].max().to_pydatetime()
        if isinstance(as_of, datetime):
            return as_of
        return pd.to_datetime(as_of).to_pydatetime()
