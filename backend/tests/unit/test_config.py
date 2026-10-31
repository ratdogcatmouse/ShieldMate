"""Config.load: flags are forgiving about case, a mistyped ALERT_SOURCE fails at start-up."""
import pytest

from config import Config


def load(**env):
    return Config.load(env_file=None, environ=env)


@pytest.mark.parametrize("value, expected", [("1", True), ("TRUE", True), ("Yes", True), ("on", True),
                                              ("0", False), ("", False), ("nope", False)])
def test_flag_spellings(value, expected):
    assert load(ACTIONS=value).actions is expected


def test_defaults_keep_the_replay_demo():
    c = load()
    assert (c.alert_source, c.actions, c.ai_reword, c.owner_pin) == ("replay", False, False, "")


def test_a_mistyped_alert_source_is_rejected():
    with pytest.raises(ValueError, match="ALERT_SOURCE"):
        load(ALERT_SOURCE="live")
