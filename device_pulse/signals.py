"""The three Device Pulse signals.

Each function takes already-windowed data and returns a SignalResult. Keeping
these pure (no I/O, no time handling) makes them easy to unit-test.
"""

from __future__ import annotations

from collections import Counter
from typing import List, Sequence

from .config import PulseConfig
from .models import SignalResult


# --------------------------------------------------------------------------
# Signal 1 — Frequency: recent event rate vs historical rate
# --------------------------------------------------------------------------
def compute_frequency(
    recent_count: int,
    baseline_count: int,
    cfg: PulseConfig,
) -> SignalResult:
    recent_rate = recent_count / cfg.recent_window_days
    baseline_rate = baseline_count / cfg.baseline_window_days

    if baseline_rate > 0:
        ratio = recent_rate / baseline_rate
        basis = "ratio"
    else:
        # No historical activity to compare against: grade on raw recent volume.
        ratio = float("inf") if recent_count > 0 else 1.0
        basis = "new_activity"

    if basis == "ratio":
        if ratio >= cfg.freq_critical_ratio:
            label, points = "Critical", 3.0
        elif ratio >= cfg.freq_high_ratio:
            label, points = "High", 2.0
        elif ratio >= cfg.freq_elevated_ratio:
            label, points = "Elevated", 1.0
        else:
            label, points = "Normal", 0.0
        explanation = (
            f"Recent rate {recent_rate:.3f}/day vs baseline {baseline_rate:.3f}/day "
            f"= {ratio:.2f}x."
        )
    else:
        # Brand-new signal source with no baseline.
        if recent_count >= cfg.freq_new_activity_critical_count:
            label, points = "Critical", 3.0
        elif recent_count >= cfg.freq_new_activity_high_count:
            label, points = "High", 2.0
        elif recent_count > 0:
            label, points = "Elevated", 1.0
        else:
            label, points = "Normal", 0.0
        explanation = (
            f"No baseline events; {recent_count} recent events treated as new activity."
        )

    reported_ratio = ratio if ratio != float("inf") else 999.0
    return SignalResult(
        name="frequency",
        label=label,
        value=reported_ratio,
        points=points,
        detail={
            "recent_count": recent_count,
            "baseline_count": baseline_count,
            "recent_rate_per_day": round(recent_rate, 4),
            "baseline_rate_per_day": round(baseline_rate, 4),
            "basis": basis,
        },
        explanation=explanation,
    )


# --------------------------------------------------------------------------
# Signal 2 — Severity: average recent severity vs historical
# --------------------------------------------------------------------------
def compute_severity(
    recent_severities: Sequence[float],
    baseline_severities: Sequence[float],
    cfg: PulseConfig,
) -> SignalResult:
    recent_avg = _mean(recent_severities)
    baseline_avg = _mean(baseline_severities)
    delta = recent_avg - baseline_avg

    if recent_avg >= cfg.sev_escalating_absolute:
        label, points = "Escalating", 2.0
        explanation = (
            f"Recent avg severity {recent_avg:.2f} is at/above the escalation floor "
            f"({cfg.sev_escalating_absolute})."
        )
    elif delta >= cfg.sev_escalating_delta:
        label, points = "Escalating", 2.0
        explanation = f"Avg severity rose {delta:+.2f} ({baseline_avg:.2f} -> {recent_avg:.2f})."
    elif delta >= cfg.sev_worsening_delta:
        label, points = "Worsening", 1.0
        explanation = f"Avg severity rose {delta:+.2f} ({baseline_avg:.2f} -> {recent_avg:.2f})."
    else:
        label, points = "Stable", 0.0
        explanation = f"Avg severity {recent_avg:.2f} vs baseline {baseline_avg:.2f} (delta {delta:+.2f})."

    return SignalResult(
        name="severity",
        label=label,
        value=delta,
        points=points,
        detail={
            "recent_avg_severity": round(recent_avg, 3),
            "baseline_avg_severity": round(baseline_avg, 3),
            "scale_max": cfg.severity_scale_max,
        },
        explanation=explanation,
    )


# --------------------------------------------------------------------------
# Signal 3 — Pattern concentration: dominant failure code in recent events
# --------------------------------------------------------------------------
def compute_pattern(
    recent_codes: Sequence[str],
    baseline_codes: Sequence[str],
    cfg: PulseConfig,
) -> SignalResult:
    n_recent = len(recent_codes)
    if n_recent == 0:
        return SignalResult(
            name="pattern",
            label="Distributed",
            value=0.0,
            points=0.0,
            detail={"top_code": None, "hhi": 0.0},
            explanation="No recent events.",
        )

    recent_counts = Counter(recent_codes)
    top_code, top_n = recent_counts.most_common(1)[0]
    top_share = top_n / n_recent

    # Herfindahl-Hirschman Index as an auxiliary concentration measure.
    hhi = sum((c / n_recent) ** 2 for c in recent_counts.values())

    # How present was this code historically? Low baseline share + rising = emerging.
    baseline_counts = Counter(baseline_codes)
    n_baseline = len(baseline_codes)
    top_baseline_share = (baseline_counts.get(top_code, 0) / n_baseline) if n_baseline else 0.0
    is_emerging_code = (
        top_baseline_share <= cfg.pattern_emerging_baseline_share_max
        and top_share >= cfg.pattern_emerging_min_share
    )

    if top_share >= cfg.pattern_dominant_min:
        label, points = "Dominant", 3.0
    elif top_share >= cfg.pattern_concentrated_min:
        label, points = "Concentrated", 2.0
    elif top_share >= cfg.pattern_distributed_max or is_emerging_code:
        label, points = "Emerging", 1.0
    else:
        label, points = "Distributed", 0.0

    explanation = (
        f"Top code '{top_code}' is {top_share:.0%} of recent events "
        f"(baseline share {top_baseline_share:.0%}; HHI {hhi:.2f})."
    )
    if is_emerging_code and label == "Emerging":
        explanation += " Rising code with little baseline history."

    return SignalResult(
        name="pattern",
        label=label,
        value=top_share,
        points=points,
        detail={
            "top_code": top_code,
            "top_code_count": top_n,
            "top_code_baseline_share": round(top_baseline_share, 3),
            "distinct_recent_codes": len(recent_counts),
            "hhi": round(hhi, 3),
            "is_emerging_code": is_emerging_code,
        },
        explanation=explanation,
    )


def _mean(values: Sequence[float]) -> float:
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else 0.0
