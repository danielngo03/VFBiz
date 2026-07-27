from collections.abc import Mapping
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


class JsonSchemaReleaseAuthorityValidator:
    """Compile and apply the canonical release-authority JSON Schema."""

    def __init__(self, schema: Mapping[str, Any]) -> None:
        Draft202012Validator.check_schema(schema)
        self._validator = Draft202012Validator(
            dict(schema),
            format_checker=FormatChecker(),
        )

    def validate(self, document: Mapping[str, Any]) -> None:
        self._validator.validate(dict(document))  # pyright: ignore[reportUnknownMemberType]
