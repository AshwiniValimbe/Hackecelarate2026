"""Device Pulse - demo web server.

A thin Flask layer over the existing device_pulse engine. It serves a fleet
monitoring dashboard and a JSON API. Run:

    python -m pip install -r requirements.txt
    python app.py

then open http://127.0.0.1:5000
"""

from __future__ import annotations

import io
import os
import sys

import pandas as pd
from flask import Flask, jsonify, render_template, request

from device_pulse import DevicePulse

# Make the sample-data generator importable without turning examples into a package.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "examples"))
import generate_sample_data as sample  # noqa: E402

app = Flask(__name__)
pulse = DevicePulse()

# Demo default: the synthetic fleet, analysed as of the generator's reference date.
DEFAULT_AS_OF = sample.AS_OF.date().isoformat()


def _payload(assessments, as_of, source):
    rows = [a.to_dict() for a in assessments]
    counts = {"Healthy": 0, "Watch": 0, "At Risk": 0, "Critical": 0}
    for a in assessments:
        counts[a.status] = counts.get(a.status, 0) + 1
    return {
        "as_of": as_of,
        "source": source,
        "counts": counts,
        "total": len(assessments),
        "devices": rows,
    }


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/fleet")
def fleet():
    """Analyse the built-in synthetic fleet."""
    as_of = request.args.get("as_of", DEFAULT_AS_OF)
    events_df = sample.build_events()
    devices_df = sample.build_devices()
    assessments = pulse.assess_fleet(events_df, devices_df, as_of=as_of)
    return jsonify(_payload(assessments, as_of, source="sample fleet"))


@app.route("/device/<device_id>")
def device_page(device_id):
    """A focused page for a single device (sample fleet)."""
    return render_template("device.html", device_id=device_id)


@app.route("/api/device/<device_id>")
def device_detail(device_id):
    """Assessment + recent event log for one device of the sample fleet."""
    as_of = request.args.get("as_of", DEFAULT_AS_OF)
    # Build events once and reuse, so the assessment and the listed recent
    # events are computed from exactly the same data.
    events_df = sample.build_events()
    devices_df = sample.build_devices()
    assessments = pulse.assess_fleet(events_df, devices_df, as_of=as_of)
    match = next((a for a in assessments if a.device_id == device_id), None)
    if match is None:
        return jsonify({"error": f"Unknown device '{device_id}'."}), 404
    recent = pulse.recent_events(events_df, device_id, as_of=match.as_of)
    events = [
        {
            "timestamp": ts.isoformat(),
            "event_code": code,
            "severity": sev,
            "patient_impact": impact,
        }
        for ts, code, sev, impact in zip(
            recent["timestamp"], recent["event_code"],
            recent["severity"], recent["patient_impact"],
        )
    ]
    return jsonify({
        "source": "sample fleet",
        "as_of": match.as_of,
        "window_days": pulse.cfg.recent_window_days,
        "device": match.to_dict(),
        "recent_events": events,
    })


@app.route("/api/analyze", methods=["POST"])
def analyze():
    """Analyse an uploaded event log (and optional device registry)."""
    if "events" not in request.files or request.files["events"].filename == "":
        return jsonify({"error": "Upload an events CSV to analyse."}), 400
    try:
        events_df = pd.read_csv(io.BytesIO(request.files["events"].read()))
        devices_df = None
        if "devices" in request.files and request.files["devices"].filename:
            devices_df = pd.read_csv(io.BytesIO(request.files["devices"].read()))
        as_of = request.form.get("as_of") or None
        assessments = pulse.assess_fleet(events_df, devices_df, as_of=as_of)
    except Exception as exc:  # surface a readable message to the UI
        return jsonify({"error": f"Could not analyse that file: {exc}"}), 400
    resolved = assessments[0].as_of if assessments else (as_of or DEFAULT_AS_OF)
    return jsonify(_payload(assessments, resolved, source="uploaded log"))


if __name__ == "__main__":
    app.run(debug=True, port=5000)
