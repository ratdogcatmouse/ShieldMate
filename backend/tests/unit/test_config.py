"""Config.load: flags are forgiving about case, a mistyped ALERT_SOURCE fails at start-up."""
import pytest

import config as config_module
from config import Config


@pytest.fixture(autouse=True)
def no_local_env(tmp_path, monkeypatch):
    """Config.load(env_file=None) falls back to the real backend/.env, so a laptop's lab settings
    (ALERT_SOURCE=wazuh, ACTIONS=1, SEED_PATH=...) would leak into these tests. Point it at an
    empty file instead; ``load`` below also passes the environment explicitly."""
    monkeypatch.setattr(config_module, "BACKEND_DIR", tmp_path)


def load(**env):
    return Config.load(environ=env)


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


def test_seed_path_defaults_to_the_demo_seed():
    assert load().seed_path == config_module.REPO_ROOT / "backend" / "seed" / "clinic.json"


def test_seed_path_is_read_from_the_environment_relative_to_the_repo_root():
    c = load(SEED_PATH="backend/seed/clinic.lab.json")
    assert c.seed_path == config_module.REPO_ROOT / "backend" / "seed" / "clinic.lab.json"
    assert c.seed_path.is_file()                      # the committed lab seed really exists
