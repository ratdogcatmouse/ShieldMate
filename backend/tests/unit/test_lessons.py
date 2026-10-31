"""Lesson engine: placeholders, role text, translations with English fallback, T0.06-style validation."""
import copy
import json

import pytest

from config import Config
from lessons.engine import LessonBook, LessonError, fill

RAW = json.loads(Config().lessons_path.read_text())
VALUES = {"agent_name": "RECEPTION-PC", "count": 8, "window_minutes": 4}


def test_fill_leaves_unknown_braces_alone():
    assert fill("{agent_name} {nope}", {"agent_name": "A"}) == "A {nope}"


def test_committed_lessons_load():
    book = LessonBook(RAW)
    assert book.rule_ids == ["60204", "100201"]


def test_role_wording_differs_and_missing_role_is_omitted():
    book = LessonBook(RAW)
    lesson = book.get("60204")
    fd = book.card_for(lesson, "front_desk", "en", VALUES, {})
    owner = book.card_for(lesson, "owner", "en", VALUES, {})
    assert fd["steps"] != owner["steps"] and "RECEPTION-PC" in fd["headline"]
    assert book.card_for(book.get("100201"), "front_desk", "en", VALUES, {}) is None


def test_log_fields_limited_to_show_log_fields():
    book = LessonBook(RAW)
    logs = {"username_tried": "x", "source_ip": "1.2.3.4"}
    assert book.card_for(book.get("60204"), "front_desk", "en", VALUES, logs)["log_fields"] == {"username_tried": "x"}
    assert set(book.card_for(book.get("60204"), "owner", "en", VALUES, logs)["log_fields"]) == {"username_tried", "source_ip"}


def test_translation_falls_back_to_english_per_string():
    data = copy.deepcopy(RAW)
    data[0]["roles"]["front_desk"]["translations"] = {"hi": {"headline": "हिंदी {agent_name}"}}
    book = LessonBook(data)
    card = book.card_for(book.get("60204"), "front_desk", "hi", VALUES, {})
    assert card["headline"] == "हिंदी RECEPTION-PC"
    assert card["why"] == "One correct guess opens patient records."          # English fallback
    assert [s["action"] for s in card["steps"]] == ["DONT_USE_DEVICE", "CALL_SAVED_IT", "NOTIFY_OWNER"]


def test_empty_translations_give_english_card():
    book = LessonBook(RAW)
    assert book.card_for(book.get("60204"), "front_desk", "kn", VALUES, {})["lang"] == "kn"


@pytest.mark.parametrize("mutate", [
    lambda d: d[0]["roles"]["owner"]["steps"].append({"action": "NOPE", "text": "x"}),
    lambda d: d[0]["roles"]["owner"].update(headline="{surprise}"),
    lambda d: d.append(copy.deepcopy(d[0])),
    lambda d: d[0].update(severity="loud"),
])
def test_invalid_lessons_are_rejected(mutate):
    data = copy.deepcopy(RAW)
    mutate(data)
    with pytest.raises(LessonError):
        LessonBook(data)
