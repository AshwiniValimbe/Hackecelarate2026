"""Command-line interface for Device Pulse.

Examples
--------
    python -m device_pulse.cli --events events.csv --devices devices.csv
    python -m device_pulse.cli --events events.csv --as-of 2026-07-12 --output report.csv
    python -m device_pulse.cli --events events.csv --json report.json --min-status Watch
"""

from __future__ import annotations

import argparse
import json
import sys

from .config import PulseConfig
from .engine import DevicePulse

_STATUS_ORDER = {"Healthy": 0, "Watch": 1, "At Risk": 2, "Critical": 3}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="device-pulse",
        description="Predictive maintenance intelligence for medical devices.",
    )
    p.add_argument("--events", required=True, help="Path to event-log CSV.")
    p.add_argument("--devices", help="Path to device registry CSV (optional).")
    p.add_argument("--as-of", help="Analysis reference date YYYY-MM-DD (default: latest event).")
    p.add_argument("--output", help="Write the fleet report CSV to this path.")
    p.add_argument("--json", dest="json_path", help="Write full JSON assessments to this path.")
    p.add_argument(
        "--min-status",
        choices=list(_STATUS_ORDER),
        default="Healthy",
        help="Only print devices at or above this status.",
    )
    p.add_argument("--recent-days", type=int, help="Override recent window (days).")
    p.add_argument("--baseline-days", type=int, help="Override baseline window (days).")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    cfg = PulseConfig()
    if args.recent_days:
        cfg.recent_window_days = args.recent_days
    if args.baseline_days:
        cfg.baseline_window_days = args.baseline_days

    pulse = DevicePulse(cfg)
    assessments = pulse.assess_fleet(args.events, args.devices, args.as_of)

    threshold = _STATUS_ORDER[args.min_status]
    shown = [a for a in assessments if _STATUS_ORDER[a.status] >= threshold]

    _print_console(shown, total=len(assessments))

    if args.output:
        pulse.fleet_report(assessments).to_csv(args.output, index=False)
        print(f"\nFleet report written to {args.output}")
    if args.json_path:
        with open(args.json_path, "w") as fh:
            json.dump([a.to_dict() for a in assessments], fh, indent=2, default=str)
        print(f"Full JSON written to {args.json_path}")
    return 0


def _print_console(assessments, total: int) -> None:
    print(f"\nDevice Pulse - {total} device(s) analysed, showing {len(assessments)}\n")
    header = f"{'DEVICE':<12}{'STATUS':<10}{'RISK':>6}  {'FREQ':<9}{'SEV':<11}{'PATTERN':<13}{'AGE':>5}"
    print(header)
    print("-" * len(header))
    for a in assessments:
        age = "-" if a.age_years is None else f"{a.age_years:.1f}"
        print(
            f"{a.device_id:<12}{a.status:<10}{a.risk_score:>6.1f}  "
            f"{a.frequency.label:<9}{a.severity.label:<11}{a.pattern.label:<13}{age:>5}"
        )
    print()
    for a in assessments:
        if a.status != "Healthy":
            print(f"[{a.device_id}] {a.status} - {a.recommended_action}")
            for r in a.reasons:
                print(f"    - {r}")


if __name__ == "__main__":
    sys.exit(main())
