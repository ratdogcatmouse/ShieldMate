"""Impact meter: step device states x seed services (T2.06, the design's Appendix A table)."""
from __future__ import annotations

from drills import impact

# The seed's devices, services and when_down notes decoded the way db.devices() returns them.
DEVICES = [
    {"agent_name": "RECEPTION-PC", "services": ["Front-desk check-in"],
     "when_down": {"Front-desk check-in": "Check-in moves to the billing PC"}},
    {"agent_name": "FILE-SERVER", "services": ["Appointments", "Billing", "Patient records"],
     "when_down": {}},
    {"agent_name": "DOCTOR-PC", "services": ["Consultations"], "when_down": {}},
]


def test_step_s1_compromised_devices_show_moved_and_down():
    step = {"devices": {"RECEPTION-PC": "infected", "FILE-SERVER": "encrypting"}}
    out = {d["device"]: d for d in impact.step_impact(step, DEVICES)}
    # RECEPTION-PC is infected but its check-in has a when_down note -> it moves.
    assert out["RECEPTION-PC"]["services"] == [
        {"name": "Front-desk check-in", "status": "moved", "note": "Check-in moves to the billing PC"}]
    # FILE-SERVER is encrypting with no notes -> all three services are down.
    assert out["FILE-SERVER"]["services"] == [
        {"name": "Appointments", "status": "down"},
        {"name": "Billing", "status": "down"},
        {"name": "Patient records", "status": "down"}]
    # DOCTOR-PC is not in the step -> stays ok.
    assert out["DOCTOR-PC"] == {"device": "DOCTOR-PC", "state": "ok",
                                 "services": [{"name": "Consultations", "status": "ok"}]}


def test_every_compromised_state_is_handled():
    for state in ("infected", "isolated", "encrypting", "encrypted"):
        out = {d["device"]: d["services"] for d in impact.step_impact(
            {"devices": {"FILE-SERVER": state}}, DEVICES)}
        assert out["FILE-SERVER"] == [{"name": s, "status": "down"} for s in
                                       ("Appointments", "Billing", "Patient records")]


def test_no_devices_declared_means_everything_ok():
    out = impact.step_impact({}, DEVICES)
    assert [d["state"] for d in out] == ["ok", "ok", "ok"]


def test_device_order_follows_the_seed():
    out = impact.step_impact({"devices": {}}, DEVICES)
    assert [d["device"] for d in out] == ["RECEPTION-PC", "FILE-SERVER", "DOCTOR-PC"]
