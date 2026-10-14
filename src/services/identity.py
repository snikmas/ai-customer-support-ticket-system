"""Minimal, privacy-safe display identities.

A ticket list or comment thread should show a human-readable name instead of a
raw database id, but it must not turn a name into a directory lookup: no email,
phone, role, or account state leaks through these helpers. Names are resolved
one id at a time from the stored user row, so an author outside the first
directory page is still found, and a deleted or missing account has an explicit
fallback instead of an empty string.
"""

from src import constants


def display_name(user, *, source=None) -> str | None:
    if user is None:
        if source == constants.Source.SYSTEM:
            return "System"
        return "Unknown user"
    if user.deleted_at is not None or user.user_status != constants.UserStatus.ACTIVE:
        return "Deleted user"
    full = f"{user.first_name} {user.last_name}".strip()
    return full or user.nickname
