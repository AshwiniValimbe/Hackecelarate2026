"""Device Pulse - predictive maintenance intelligence for medical devices.

Reads recent event-log data per device against its historical baseline and
computes three signals (Frequency, Severity, Pattern Concentration), an
age-adjusted risk score, and a fleet-ranked maintenance priority.
"""

from .config import PulseConfig, DEFAULT_CONFIG
from .engine import DevicePulse
from .models import DeviceAssessment, SignalResult
from .signals import compute_frequency, compute_severity, compute_pattern

__version__ = "0.1.0"

__all__ = [
    "DevicePulse",
    "PulseConfig",
    "DEFAULT_CONFIG",
    "DeviceAssessment",
    "SignalResult",
    "compute_frequency",
    "compute_severity",
    "compute_pattern",
]
