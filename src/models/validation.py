import unicodedata
from typing import Annotated

from pydantic import AfterValidator, BeforeValidator, EmailStr, Field, HttpUrl, TypeAdapter
from pydantic.types import StringConstraints


def _reject_control_characters(value: str) -> str:
    if any(unicodedata.category(character).startswith("C") for character in value):
        raise ValueError("control_characters_not_allowed")
    return value


def _validate_http_url(value: str) -> str:
    TypeAdapter(HttpUrl).validate_python(value)
    return value


def _require_string(value: object) -> str:
    # BeforeValidators run before type coercion, so a raw non-string (int, list,
    # dict, bool, ...) would reach .strip() and raise AttributeError, which
    # Pydantic does not convert into a ValidationError. Reject it explicitly so
    # the request fails with a 422 instead of a 500.
    if not isinstance(value, str):
        raise ValueError("value_must_be_a_string")
    return value


def _strip(value: object) -> str:
    return _require_string(value).strip()


def _normalize_nickname(value: object) -> str:
    return _require_string(value).strip().lower()


Nickname = Annotated[
    str,
    BeforeValidator(_normalize_nickname),
    StringConstraints(
        min_length=3,
        max_length=32,
        pattern=r"^[a-z0-9](?:[a-z0-9_-]{1,30}[a-z0-9])$",
    ),
]
PersonName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=50),
    AfterValidator(_reject_control_characters),
]
EmailAddress = Annotated[
    EmailStr,
    BeforeValidator(_strip),
    Field(max_length=254),
]
PhoneNumber = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=3,
        max_length=16,
        pattern=r"^\+[1-9]\d{1,14}$",
    ),
]
AvatarUrl = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=255),
    AfterValidator(_validate_http_url),
]
NewPassword = Annotated[str, StringConstraints(min_length=15, max_length=128)]
LoginPassword = Annotated[str, StringConstraints(min_length=1, max_length=128)]
TicketTitle = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=3, max_length=255),
    AfterValidator(_reject_control_characters),
]
LongBody = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=32_000),
]
EntityId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=36)]
RoutingCatalogName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=100),
    AfterValidator(_reject_control_characters),
]
RoutingCatalogDescription = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
    AfterValidator(_reject_control_characters),
]
RefreshToken = Annotated[str, StringConstraints(min_length=1, max_length=4_096)]
