import math
import re

_SHA256_PATTERN = re.compile(r"^sha256:[a-f0-9]{64}$")


def is_bounded_text(value: str, *, maximum: int = 200) -> bool:
    return (
        bool(value.strip())
        and len(value) <= maximum
        and not any(ord(character) < 32 for character in value)
    )


def is_sha256(value: str) -> bool:
    return _SHA256_PATTERN.fullmatch(value) is not None


def is_finite_non_negative(value: float) -> bool:
    return math.isfinite(value) and value >= 0
