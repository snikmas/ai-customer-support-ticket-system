from types import SimpleNamespace

from src import constants
from src.services import identity


def _user(**overrides):
    base = {
        "first_name": "Ada",
        "last_name": "Lovelace",
        "nickname": "ada",
        "deleted_at": None,
        "user_status": constants.UserStatus.ACTIVE,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_display_name_uses_full_name():
    assert identity.display_name(_user()) == "Ada Lovelace"


def test_display_name_falls_back_to_nickname_when_name_is_blank():
    assert identity.display_name(_user(first_name="", last_name="")) == "ada"


def test_display_name_marks_deleted_and_inactive_accounts():
    assert identity.display_name(_user(deleted_at="2026-01-01")) == "Deleted user"
    assert identity.display_name(_user(user_status=constants.UserStatus.DELETED)) == "Deleted user"


def test_display_name_handles_missing_and_system_actors():
    assert identity.display_name(None) == "Unknown user"
    assert identity.display_name(None, source=constants.Source.SYSTEM) == "System"
