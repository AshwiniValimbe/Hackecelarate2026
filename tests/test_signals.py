"""Unit tests for Device Pulse signal logic (pytest)."""

from device_pulse.config import PulseConfig
from device_pulse.signals import compute_frequency, compute_severity, compute_pattern
from device_pulse.engine import DevicePulse

CFG = PulseConfig()


# ------------------------------------------------------------- frequency
def test_frequency_normal():
    # recent rate ~= baseline rate
    r = compute_frequency(recent_count=8, baseline_count=24, cfg=CFG)
    assert r.label == "Normal"


def test_frequency_elevated():
    r = compute_frequency(recent_count=15, baseline_count=24, cfg=CFG)
    assert r.label == "Elevated"


def test_frequency_critical():
    r = compute_frequency(recent_count=40, baseline_count=15, cfg=CFG)
    assert r.label == "Critical"


def test_frequency_no_baseline_grades_on_volume():
    r = compute_frequency(recent_count=20, baseline_count=0, cfg=CFG)
    assert r.label == "Critical"
    assert r.detail["basis"] == "new_activity"


# -------------------------------------------------------------- severity
def test_severity_stable():
    r = compute_severity([2, 2, 3], [2, 3, 2], CFG)
    assert r.label == "Stable"


def test_severity_worsening():
    # delta ~0.67 -> Worsening band (0.5 <= delta < 1.0)
    r = compute_severity([3, 3, 2], [2, 2, 2], CFG)
    assert r.label == "Worsening"


def test_severity_escalating_by_delta():
    r = compute_severity([4, 4, 3], [2, 2, 2], CFG)
    assert r.label == "Escalating"


def test_severity_escalating_by_absolute_floor():
    r = compute_severity([4, 5, 4], [4, 4, 4], CFG)  # delta ~0 but very high
    assert r.label == "Escalating"


# --------------------------------------------------------------- pattern
def test_pattern_distributed():
    recent = ["A", "B", "C", "D", "E", "A", "B"]
    r = compute_pattern(recent, ["A", "B", "C"], CFG)
    assert r.label == "Distributed"


def test_pattern_dominant():
    recent = ["X"] * 9 + ["Y"]
    r = compute_pattern(recent, ["A", "B", "X", "Y"], CFG)
    assert r.label == "Dominant"


def test_pattern_emerging_new_code():
    # 'NEW' absent from baseline, moderate recent share
    recent = ["NEW", "NEW", "NEW", "A", "B", "C", "D", "E", "F", "G"]
    baseline = ["A", "B", "C", "D", "E", "F", "G", "H"]
    r = compute_pattern(recent, baseline, CFG)
    assert r.label == "Emerging"
    assert r.detail["is_emerging_code"] is True


# ------------------------------------------------------------------- age
def test_age_factor_bands():
    p = DevicePulse(CFG)
    assert p._age_factor(3.0) == 1.00
    assert p._age_factor(7.0) == 1.15
    assert p._age_factor(9.0) == 1.30
    assert p._age_factor(12.0) == 1.50
    assert p._age_factor(None) == 1.00


def test_older_device_scores_higher():
    p = DevicePulse(CFG)
    freq = compute_frequency(20, 24, CFG)
    sev = compute_severity([3, 3], [2, 2], CFG)
    pat = compute_pattern(["A", "A", "B"], ["A", "B"], CFG)
    young = p._risk_score(freq, sev, pat, age_factor=1.0)
    old = p._risk_score(freq, sev, pat, age_factor=1.5)
    assert old > young
