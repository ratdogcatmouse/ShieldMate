"""T2.01: level below 7, or a rule with no lesson, is filtered."""
from alerts.filter import should_filter
from alerts.normalise import NormalisedAlert

LESSON = {"lesson_id": "x"}


def alert(rule_id="60204", level=10):
    return NormalisedAlert("replay", None, rule_id, level, "RECEPTION-PC", "2026-11-01T04:00:00Z")


def test_low_level_is_filtered_even_with_a_lesson():
    assert should_filter(alert(level=3), LESSON)


def test_no_lesson_is_filtered_even_at_high_level():
    assert should_filter(alert("550", 7), None)       # rule 550: level 7 but no lesson


def test_level_seven_with_lesson_is_kept():
    assert not should_filter(alert(level=7), LESSON)


def test_real_alerts_from_the_replay_file(app_h):
    """60106 (level 3) and 550 (no lesson) filter; 60204 and 100201 don't."""
    lessons = app_h.ctx.lessons
    assert should_filter(alert("60106", 3), lessons.get("60106"))
    assert should_filter(alert("550", 7), lessons.get("550"))
    assert not should_filter(alert("60204", 10), lessons.get("60204"))
    assert not should_filter(alert("100201", 12), lessons.get("100201"))
