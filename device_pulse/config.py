"""Configuration for Device Pulse.

Every threshold the engine uses lives here so the scoring logic stays
transparent and tunable. Fleet managers / manufacturers can override any of
these without touching the algorithm.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict


@dataclass
class PulseConfig:
    # ---- Analysis windows (in days) ------------------------------------
    recent_window_days: int = 90          # "recent" = last 90 days
    baseline_window_days: int = 270       # "9 month historical baseline"

    # ---- Data sufficiency guards ---------------------------------------
    # Below these counts we refuse to raise alarms confidently.
    min_recent_events: int = 3
    min_baseline_events: int = 5

    # ---- Frequency signal (recent rate / baseline rate) ----------------
    # Labels: Normal < Elevated < High < Critical
    freq_elevated_ratio: float = 1.25
    freq_high_ratio: float = 2.00
    freq_critical_ratio: float = 3.50
    # If baseline had ~zero events, use recent absolute count to grade.
    freq_new_activity_high_count: int = 8
    freq_new_activity_critical_count: int = 15

    # ---- Severity signal (recent avg severity vs baseline) -------------
    # Severity is a numeric scale (default 1..5). Labels: Stable/Worsening/Escalating
    severity_scale_max: int = 5
    sev_worsening_delta: float = 0.5      # recent avg is this much higher
    sev_escalating_delta: float = 1.0
    # Absolute floor: very high recent severity escalates regardless of delta.
    sev_escalating_absolute: float = 4.0
    # Map categorical severity strings -> numeric (case-insensitive).
    severity_map: Dict[str, int] = field(default_factory=lambda: {
        "informational": 1, "info": 1,
        "minor": 2, "low": 2,
        "moderate": 3, "medium": 3, "warning": 3,
        "major": 4, "high": 4, "error": 4,
        "critical": 5, "severe": 5, "fatal": 5,
    })

    # ---- Pattern concentration signal ----------------------------------
    # Based on the share of the single most frequent recent failure code.
    # Labels: Distributed < Emerging < Concentrated < Dominant
    pattern_distributed_max: float = 0.35   # below this = Distributed
    pattern_concentrated_min: float = 0.50
    pattern_dominant_min: float = 0.65
    # "Emerging": a code with little/no baseline history rising quickly.
    pattern_emerging_baseline_share_max: float = 0.10
    pattern_emerging_min_share: float = 0.25

    # ---- Device age -----------------------------------------------------
    # Devices older than this get an age risk multiplier applied to the score.
    age_threshold_years: float = 6.0
    age_factor_bands: list = field(default_factory=lambda: [
        # (upper_bound_years, multiplier)
        (6.0, 1.00),
        (8.0, 1.15),
        (10.0, 1.30),
        (float("inf"), 1.50),
    ])
    end_of_life_watch_years: float = 8.0

    # ---- Signal weights for the overall risk score ---------------------
    # Severity is weighted highest: on a patient-facing analyser, worsening
    # severity matters more than raw chatter.
    weight_frequency: float = 1.0
    weight_severity: float = 1.5
    weight_pattern: float = 1.0

    # ---- Overall status bands (0..100 risk score) ----------------------
    status_watch_min: float = 20.0
    status_at_risk_min: float = 45.0
    status_critical_min: float = 70.0


DEFAULT_CONFIG = PulseConfig()
