from dataclasses import dataclass
from typing import Literal, Protocol

ReleasePointerTargetKind = Literal["activation", "static_safe_release"]


@dataclass(frozen=True, slots=True)
class ActiveReleasePointer:
    """What the release-pointer table currently claims is active.

    This is a raw fact read, not a verified release: it carries no proof that
    the referenced activation/static-safe release actually passed gate,
    approval, promotion or live-control checks. Only
    `ReleaseManifestResolver.resolve()` (which additionally requires a
    trusted artifact/evidence registry that does not exist in this codebase
    yet) produces a verified result. Callers must not treat this as
    release-authority approval.
    """

    assistant_profile: str
    environment: str
    target_kind: ReleasePointerTargetKind
    activation_id: str | None
    candidate_sha256: str | None
    safe_release_id: str | None
    envelope_sha256: str
    pointer_revision: int

    def __post_init__(self) -> None:
        if self.target_kind == "activation":
            if (
                self.activation_id is None
                or self.candidate_sha256 is None
                or self.safe_release_id is not None
            ):
                raise ValueError(
                    "an activation pointer must carry activation_id and candidate_sha256"
                )
        elif (
            self.safe_release_id is None
            or self.activation_id is not None
            or self.candidate_sha256 is not None
        ):
            raise ValueError("a static-safe-release pointer must carry safe_release_id only")
        if self.candidate_sha256 is not None and (
            len(self.candidate_sha256) != 64
            or any(
                character not in "0123456789abcdef"
                for character in self.candidate_sha256
            )
        ):
            raise ValueError("candidate_sha256 must be a SHA-256 hex digest")
        if len(self.envelope_sha256) != 64 or any(
            character not in "0123456789abcdef" for character in self.envelope_sha256
        ):
            raise ValueError("envelope_sha256 must be a SHA-256 hex digest")
        if self.pointer_revision < 0:
            raise ValueError("pointer_revision cannot be negative")


class ActiveReleasePointerStore(Protocol):
    async def current(
        self,
        *,
        assistant_profile: str,
        environment: str,
    ) -> ActiveReleasePointer | None:
        """The pointer currently on file for this scope, or None if unset."""
        ...
