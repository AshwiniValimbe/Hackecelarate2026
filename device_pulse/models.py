"""Result data structures returned by the engine."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


@dataclass
class SignalResult:
    """One of the three signals for a single device."""
    name: str                      # "frequency" | "severity" | "pattern"
    label: str                     # e.g. "Elevated", "Escalating", "Dominant"
    value: float                   # the headline metric (ratio / delta / share)
    points: float                  # contribution to the risk score (pre-weight)
    detail: Dict[str, Any] = field(default_factory=dict)
    explanation: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DeviceAssessment:
    """Full Device Pulse read-out for one device."""
    device_id: str
    model: Optional[str]
    as_of: str

    age_years: Optional[float]
    age_factor: float
    end_of_life_watch: bool

    recent_event_count: int
    baseline_event_count: int
    data_sufficient: bool

    frequency: SignalResult
    severity: SignalResult
    pattern: SignalResult

    risk_score: float              # 0..100
    status: str                    # Healthy | Watch | At Risk | Critical
    recommended_action: str
    reasons: List[str] = field(default_factory=list)

    # ---- Patient impact (informational; does NOT affect risk_score) ------
    criticality: Optional[str] = None            # device care tier
    patient_impact: Dict[str, Any] = field(default_factory=dict)  # recent rollup

    def summary_row(self) -> Dict[str, Any]:
        """Flat dict suitable for a fleet DataFrame / CSV export."""
        return {
            "device_id": self.device_id,
            "model": self.model,
            "as_of": self.as_of,
            "age_years": None if self.age_years is None else round(self.age_years, 2),
            "age_factor": self.age_factor,
            "eol_watch": self.end_of_life_watch,
            "recent_events": self.recent_event_count,
            "baseline_events": self.baseline_event_count,
            "data_sufficient": self.data_sufficient,
            "frequency": self.frequency.label,
            "freq_ratio": round(self.frequency.value, 2),
            "severity": self.severity.label,
            "sev_delta": round(self.severity.value, 2),
            "pattern": self.pattern.label,
            "top_code": self.pattern.detail.get("top_code"),
            "top_code_share": round(self.pattern.value, 2),
            "risk_score": round(self.risk_score, 1),
            "status": self.status,
            "criticality": self.criticality,
            "patient_impact_worst": self.patient_impact.get("worst"),
            "patient_impact_events": self.patient_impact.get("elevated_count"),
            "recommended_action": self.recommended_action,
        }

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["frequency"] = self.frequency.to_dict()
        d["severity"] = self.severity.to_dict()
        d["pattern"] = self.pattern.to_dict()
        return d
