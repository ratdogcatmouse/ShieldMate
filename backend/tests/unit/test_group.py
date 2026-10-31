"""T2.02: same rule and PC within 10 minutes bumps the count (8+ to 12+); after 10 minutes a new card."""
from alerts.group import next_count
from alerts.normalise import NormalisedAlert


def alert(counts=None):
    return NormalisedAlert("replay", None, "60204", 10, "RECEPTION-PC", "t", counts=counts or {})


def test_explicit_higher_count_replaces():
    assert next_count(8, alert({"count": 12})) == 12


def test_no_explicit_count_bumps_by_one():
    assert next_count(8, alert()) == 9


def test_explicit_count_not_higher_still_bumps():
    assert next_count(12, alert({"count": 8})) == 13


def test_within_ten_minutes_groups_after_ten_makes_a_new_card(app_h):
    app_h.reset()
    app_h.inject("password_guessing")
    app_h.advance(9 * 60)
    assert app_h.inject("password_guessing")["grouped"] == 1
    cards = app_h.get("/alerts?role=owner").json()["alerts"]
    assert len(cards) == 1 and cards[0]["count"] == 12
    assert "12+" in cards[0]["card"]["what_we_know"] and "6 minutes" in cards[0]["card"]["what_we_know"]


def test_after_ten_minutes_a_new_card(make_app):
    h = make_app()
    h.reset()
    h.inject("password_guessing")
    h.advance(11 * 60)
    assert h.inject("password_guessing")["cards_created"] == 1
    assert len(h.get("/alerts?role=owner").json()["alerts"]) == 2
