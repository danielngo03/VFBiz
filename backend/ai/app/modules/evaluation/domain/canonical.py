from __future__ import annotations

import json
import math
from decimal import Decimal
from hashlib import sha256
from typing import cast


def canonical_json(document: dict[str, object]) -> str:
    def encode_number(value: float) -> str:
        if not math.isfinite(value):
            raise ValueError("CANONICAL_JSON_NON_FINITE_NUMBER")
        if value == 0:
            return "0"
        absolute = abs(value)
        shortest = repr(value).lower()
        if 1e-6 <= absolute < 1e21:
            fixed = format(Decimal(shortest), "f")
            return fixed.rstrip("0").rstrip(".") if "." in fixed else fixed
        if "e" not in shortest:
            shortest = format(value, ".15e")
        mantissa, exponent = shortest.split("e", 1)
        mantissa = mantissa.rstrip("0").rstrip(".")
        exponent_value = int(exponent)
        sign = "+" if exponent_value >= 0 else ""
        return f"{mantissa}e{sign}{exponent_value}"

    def encode(value: object) -> str:
        if value is None:
            return "null"
        if value is True:
            return "true"
        if value is False:
            return "false"
        if isinstance(value, int):
            return str(value)
        if isinstance(value, float):
            return encode_number(value)
        if isinstance(value, str):
            return json.dumps(value, ensure_ascii=False)
        if isinstance(value, dict):
            object_value = cast(dict[object, object], value)
            if any(not isinstance(key, str) for key in object_value):
                raise ValueError("CANONICAL_JSON_OBJECT_KEY_MUST_BE_TEXT")
            text_value = cast(dict[str, object], object_value)
            return (
                "{"
                + ",".join(
                    f"{json.dumps(key, ensure_ascii=False)}:{encode(text_value[key])}"
                    for key in sorted(text_value)
                )
                + "}"
            )
        if isinstance(value, (list, tuple)):
            items = cast(list[object] | tuple[object, ...], value)
            return "[" + ",".join(encode(item) for item in items) + "]"
        raise ValueError(f"CANONICAL_JSON_UNSUPPORTED_TYPE:{type(value).__name__}")

    return encode(document)


def digest_document(document: dict[str, object]) -> str:
    return f"sha256:{sha256(canonical_json(document).encode()).hexdigest()}"
