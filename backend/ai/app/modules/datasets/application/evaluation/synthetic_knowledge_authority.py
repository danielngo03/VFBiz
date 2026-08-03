"""Repository-owned authority digests for synthetic knowledge qualification."""

from typing import Final

GENERATOR_SOURCE_SHA256: Final[str] = (
    "2d98740d40e5f91610020f6e1b4e795fe31e006ed75bf1efb54cc6962e564856"
)
VERIFIER_SOURCE_SHA256: Final[str] = (
    "c5b7ecba39ca52140a303b462c282c290eb870b98f5394fe6a7dbc8847c8bd45"
)
AUTHORITY_REVISION: Final[str] = "synthetic-knowledge-authority-v1"

__all__ = [
    "AUTHORITY_REVISION",
    "GENERATOR_SOURCE_SHA256",
    "VERIFIER_SOURCE_SHA256",
]
