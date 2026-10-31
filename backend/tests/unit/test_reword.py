"""T3.01 log text never reaches the AI, T3.02 the guard, T3.03 no provider."""
import pytest

from lessons.providers import NoneProvider
from lessons.reword import output_ok, reword

LESSON = {"fallback_reword": {"headline": "Someone keeps trying {agent_name}.", "why": "They can open records."}}
VALUES = {"agent_name": "RECEPTION-PC"}
H, W = "Someone is guessing the password on RECEPTION-PC. 8 tries.", "One guess opens patient records."


class Spy:
    def __init__(self, out=None):
        self.calls, self.out = [], out

    def reword(self, headline, why):
        self.calls.append((headline, why))
        return self.out or (headline, why)


def test_provider_gets_exactly_the_two_strings():
    spy = Spy()
    reword(spy, H, W, LESSON, VALUES)
    assert spy.calls == [(H, W)]


def test_poisoned_username_never_reaches_provider(app_h):
    """End to end through the route, with the real poisoned replay alert."""
    from lessons.reword import reword as guard
    spy = Spy()
    app_h.reset(); app_h.inject("password_guessing")
    ctx = app_h.ctx
    row = ctx.db.one("SELECT * FROM alerts WHERE status='new'")
    from alerts import pipeline
    c = pipeline.card(ctx.lessons, row, "front_desk", "en")
    guard(spy, c["headline"], c["why"], ctx.lessons.get("60204"), {"agent_name": row["agent_name"]})
    assert "ignore previous instructions" not in repr(spy.calls)
    assert len(spy.calls) == 1 and len(spy.calls[0]) == 2


def test_good_output_is_accepted_as_ai():
    out = reword(Spy(("Somebody keeps guessing RECEPTION-PC's password, 8 times.", "A right guess opens records.")),
                 H, W, LESSON, VALUES)
    assert out["source"] == "ai"


@pytest.mark.parametrize("bad", [
    ("Someone tried 9 times on RECEPTION-PC.", W),                  # changed number
    ("Someone tried 8 times and 3 more on RECEPTION-PC.", W),       # new digits
    (H, "See https://evil.example/now"),                            # link
    (H, "visit evil.com"),                                          # bare domain
    ("x" * 201, W),                                                 # too long
    ("", W),                                                        # empty
])
def test_guard_rejects_bad_output(bad):
    assert not output_ok((H, W), bad)
    out = reword(Spy(bad), H, W, LESSON, VALUES)
    assert out == {"headline": "Someone keeps trying RECEPTION-PC.", "why": "They can open records.",
                   "source": "fallback"}


def test_no_provider_returns_fallback():
    assert reword(NoneProvider(), H, W, LESSON, VALUES)["source"] == "fallback"


def test_provider_exception_returns_fallback():
    class Boom:
        def reword(self, h, w):
            raise TimeoutError
    assert reword(Boom(), H, W, LESSON, VALUES)["source"] == "fallback"
