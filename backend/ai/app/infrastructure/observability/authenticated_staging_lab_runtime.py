"""Concrete, content-free adapters for the local authenticated staging lab."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Final, cast

from app.infrastructure.observability.authenticated_staging_lab import (
    AcceptedSyntheticEvidence,
    AuthenticatedStagingLabVerifier,
    RuntimeIdentity,
)

_PACKET_SCHEMA: Final[str] = "authenticated-staging-packet-registry-v1"
_EVIDENCE_SCHEMA: Final[str] = "authenticated-staging-evidence-registry-v1"
_AUTHORITY_CLASS: Final[str] = "synthetic-browser-lab-qualification"
_MAX_REGISTRY_BYTES: Final[int] = 64 * 1024
_SHA256_LENGTH: Final[int] = 64


class AuthenticatedStagingLabAdapterError(RuntimeError):
    """A local authority adapter is missing, malformed or unsafe."""


class LabControlDisableStatus(StrEnum):
    DISABLED = "disabled"
    ALREADY_DISABLED = "already-disabled"
    MISMATCH = "mismatch"


@dataclass(frozen=True, slots=True)
class AuthenticatedStagingLabRuntimeConfig:
    packet_registry_path: Path
    packet_registry_sha256: str
    evidence_registry_path: Path
    evidence_registry_sha256: str
    activation_database_path: Path
    runtime_identity: RuntimeIdentity

    def __post_init__(self) -> None:
        _require_sha256(self.packet_registry_sha256, self.evidence_registry_sha256)


@dataclass(frozen=True, slots=True)
class LabActivationControlSeed:
    registry_id: str
    generation: int
    control_sha256: str
    enabled: bool = True

    def __post_init__(self) -> None:
        if not self.registry_id or len(self.registry_id) > 128:
            raise ValueError("lab control registry ID is invalid")
        if self.generation < 1:
            raise ValueError("lab control generation must be positive")
        _require_sha256(self.control_sha256)


class PinnedJsonPacketRegistry:
    """Resolve one exact packet from a deployment-pinned registry artifact."""

    def __init__(self, path: Path, expected_sha256: str) -> None:
        _require_sha256(expected_sha256)
        self._path = path
        self._expected_sha256 = expected_sha256

    def is_pinned(self, packet_sha256: str) -> bool:
        try:
            _require_sha256(packet_sha256)
            document = _read_pinned_json(self._path, self._expected_sha256)
            _require_exact_keys(
                document,
                {
                    "packet_sha256",
                    "release_eligible",
                    "schema_revision",
                    "status",
                },
            )
            return (
                document["schema_revision"] == _PACKET_SCHEMA
                and document["status"] == "pinned"
                and document["release_eligible"] is False
                and document["packet_sha256"] == packet_sha256
            )
        except (AuthenticatedStagingLabAdapterError, ValueError):
            return False


class PinnedJsonSyntheticEvidenceAuthority:
    """Resolve one reviewed synthetic receipt without storing evaluated content."""

    def __init__(self, path: Path, expected_sha256: str) -> None:
        _require_sha256(expected_sha256)
        self._path = path
        self._expected_sha256 = expected_sha256

    def resolve(self, evidence_sha256: str) -> AcceptedSyntheticEvidence | None:
        try:
            _require_sha256(evidence_sha256)
            document = _read_pinned_json(self._path, self._expected_sha256)
            _require_exact_keys(
                document,
                {
                    "authority_class",
                    "evidence_sha256",
                    "human_approved",
                    "independent_review_sha256",
                    "release_eligible",
                    "schema_revision",
                    "target_release_binding_sha256",
                },
            )
            if (
                document["schema_revision"] != _EVIDENCE_SCHEMA
                or document["authority_class"] != _AUTHORITY_CLASS
                or document["evidence_sha256"] != evidence_sha256
                or document["human_approved"] is not False
                or document["release_eligible"] is not False
            ):
                return None
            target = str(document["target_release_binding_sha256"])
            review = str(document["independent_review_sha256"])
            _require_sha256(target, review)
            return AcceptedSyntheticEvidence(
                evidence_sha256=evidence_sha256,
                target_release_binding_sha256=target,
                authority_class=_AUTHORITY_CLASS,
                independent_review_sha256=review,
            )
        except (AuthenticatedStagingLabAdapterError, ValueError, TypeError):
            return None


class StaticRuntimeIdentityProvider:
    def __init__(self, identity: RuntimeIdentity) -> None:
        self._identity = identity

    def current(self) -> RuntimeIdentity:
        return self._identity


class UtcSystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class SqliteLabActivationControl:
    """Consume a pinned activation nonce once under an immediate transaction."""

    def __init__(self, path: Path) -> None:
        self._path = path

    @classmethod
    def provision(cls, path: Path, seed: LabActivationControlSeed) -> SqliteLabActivationControl:
        _prepare_new_private_file(path)
        connection = sqlite3.connect(path)
        try:
            connection.executescript(
                """
                PRAGMA journal_mode=DELETE;
                PRAGMA synchronous=FULL;
                CREATE TABLE lab_control (
                  registry_id TEXT PRIMARY KEY,
                  generation INTEGER NOT NULL CHECK (generation > 0),
                  control_sha256 TEXT NOT NULL CHECK (length(control_sha256) = 64),
                  enabled INTEGER NOT NULL CHECK (enabled IN (0, 1))
                ) STRICT;
                CREATE TABLE consumed_activation (
                  packet_sha256 TEXT NOT NULL CHECK (length(packet_sha256) = 64),
                  nonce_sha256 TEXT NOT NULL CHECK (length(nonce_sha256) = 64),
                  registry_id TEXT NOT NULL,
                  generation INTEGER NOT NULL,
                  consumed_at TEXT NOT NULL,
                  PRIMARY KEY (packet_sha256, nonce_sha256),
                  FOREIGN KEY (registry_id) REFERENCES lab_control(registry_id)
                ) STRICT;
                """
            )
            connection.execute(
                "INSERT INTO lab_control VALUES (?, ?, ?, ?)",
                (seed.registry_id, seed.generation, seed.control_sha256, int(seed.enabled)),
            )
            connection.commit()
        except BaseException:
            connection.close()
            path.unlink(missing_ok=True)
            raise
        finally:
            connection.close()
        path.chmod(0o600)
        return cls(path)

    def consume_if_enabled(
        self,
        *,
        packet_sha256: str,
        nonce_sha256: str,
        registry_id: str,
        generation: int,
        control_sha256: str,
    ) -> bool:
        try:
            _require_sha256(packet_sha256, nonce_sha256, control_sha256)
            connection = self._connect()
            try:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    """
                    SELECT generation, control_sha256, enabled
                    FROM lab_control
                    WHERE registry_id = ?
                    """,
                    (registry_id,),
                ).fetchone()
                if row != (generation, control_sha256, 1):
                    connection.rollback()
                    return False
                connection.execute(
                    """
                    INSERT INTO consumed_activation (
                      packet_sha256, nonce_sha256, registry_id,
                      generation, consumed_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        packet_sha256,
                        nonce_sha256,
                        registry_id,
                        generation,
                        datetime.now(UTC).isoformat(),
                    ),
                )
                connection.commit()
                return True
            except sqlite3.IntegrityError:
                connection.rollback()
                return False
            finally:
                connection.close()
        except (AuthenticatedStagingLabAdapterError, ValueError, sqlite3.Error):
            return False

    def disable(self, seed: LabActivationControlSeed) -> LabControlDisableStatus:
        """Fail closed without deleting activation history or evidence."""

        try:
            connection = self._connect()
            try:
                connection.execute("BEGIN IMMEDIATE")
                observed = connection.execute(
                    """
                    SELECT generation, control_sha256, enabled
                    FROM lab_control
                    WHERE registry_id = ?
                    """,
                    (seed.registry_id,),
                ).fetchone()
                if observed is None or observed[:2] != (
                    seed.generation,
                    seed.control_sha256,
                ):
                    connection.rollback()
                    return LabControlDisableStatus.MISMATCH
                if observed[2] == 0:
                    connection.rollback()
                    return LabControlDisableStatus.ALREADY_DISABLED
                cursor = connection.execute(
                    """
                    UPDATE lab_control
                    SET enabled = 0
                    WHERE registry_id = ? AND generation = ?
                      AND control_sha256 = ? AND enabled = 1
                    """,
                    (seed.registry_id, seed.generation, seed.control_sha256),
                )
                postcondition = connection.execute(
                    """
                    SELECT generation, control_sha256, enabled
                    FROM lab_control
                    WHERE registry_id = ?
                    """,
                    (seed.registry_id,),
                ).fetchone()
                if cursor.rowcount != 1 or postcondition != (
                    seed.generation,
                    seed.control_sha256,
                    0,
                ):
                    connection.rollback()
                    raise AuthenticatedStagingLabAdapterError(
                        "lab kill-switch post-condition failed"
                    )
                connection.commit()
            finally:
                connection.close()
            self._assert_disabled(seed)
            return LabControlDisableStatus.DISABLED
        except AuthenticatedStagingLabAdapterError:
            raise
        except sqlite3.Error as error:
            raise AuthenticatedStagingLabAdapterError(
                "lab kill-switch state is unknown"
            ) from error

    def _assert_disabled(self, seed: LabActivationControlSeed) -> None:
        connection = self._connect()
        try:
            observed = connection.execute(
                """
                SELECT generation, control_sha256, enabled
                FROM lab_control
                WHERE registry_id = ?
                """,
                (seed.registry_id,),
            ).fetchone()
        except sqlite3.Error as error:
            raise AuthenticatedStagingLabAdapterError(
                "lab kill-switch post-condition is unknown"
            ) from error
        finally:
            connection.close()
        if observed != (seed.generation, seed.control_sha256, 0):
            raise AuthenticatedStagingLabAdapterError(
                "lab kill-switch post-condition is not disabled"
            )

    def _connect(self) -> sqlite3.Connection:
        _require_private_regular_file(self._path)
        connection = sqlite3.connect(
            str(self._path.resolve(strict=True)),
            uri=False,
            timeout=0.25,
            isolation_level=None,
        )
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=250")
        return connection


def build_authenticated_staging_lab_verifier(
    config: AuthenticatedStagingLabRuntimeConfig,
) -> AuthenticatedStagingLabVerifier:
    """Compose local activation authority; never compose message dispatch."""

    return AuthenticatedStagingLabVerifier(
        packet_registry=PinnedJsonPacketRegistry(
            config.packet_registry_path, config.packet_registry_sha256
        ),
        runtime_identity=StaticRuntimeIdentityProvider(config.runtime_identity),
        clock=UtcSystemClock(),
        synthetic_evidence=PinnedJsonSyntheticEvidenceAuthority(
            config.evidence_registry_path, config.evidence_registry_sha256
        ),
        activation_control=SqliteLabActivationControl(config.activation_database_path),
    )


def _read_pinned_json(path: Path, expected_sha256: str) -> dict[str, object]:
    _require_private_regular_file(path)
    if path.stat().st_size > _MAX_REGISTRY_BYTES:
        raise AuthenticatedStagingLabAdapterError("lab registry is too large")
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise AuthenticatedStagingLabAdapterError("lab registry digest mismatch")
    try:
        document: object = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AuthenticatedStagingLabAdapterError("lab registry is unreadable") from error
    if not isinstance(document, dict):
        raise AuthenticatedStagingLabAdapterError("lab registry must be an object")
    return cast(dict[str, object], document)


def _require_exact_keys(document: dict[str, object], expected: set[str]) -> None:
    if set(document) != expected:
        raise AuthenticatedStagingLabAdapterError("lab registry key set mismatch")


def _prepare_new_private_file(path: Path) -> None:
    parent = path.parent
    if path.exists() or path.is_symlink():
        raise AuthenticatedStagingLabAdapterError("lab activation database already exists")
    if not parent.is_dir() or parent.is_symlink():
        raise AuthenticatedStagingLabAdapterError("lab activation directory is unsafe")
    if parent.stat().st_mode & 0o077:
        raise AuthenticatedStagingLabAdapterError("lab activation directory is not private")


def _require_private_regular_file(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise AuthenticatedStagingLabAdapterError("lab authority file is unsafe")
    metadata = path.lstat()
    if metadata.st_nlink != 1 or metadata.st_mode & 0o077:
        raise AuthenticatedStagingLabAdapterError("lab authority file is not private")


def _require_sha256(*values: str) -> None:
    if any(
        len(value) != _SHA256_LENGTH
        or any(character not in "0123456789abcdef" for character in value)
        for value in values
    ):
        raise ValueError("lab authority digest must be lowercase SHA-256")


__all__ = [
    "AuthenticatedStagingLabAdapterError",
    "AuthenticatedStagingLabRuntimeConfig",
    "LabActivationControlSeed",
    "LabControlDisableStatus",
    "PinnedJsonPacketRegistry",
    "PinnedJsonSyntheticEvidenceAuthority",
    "SqliteLabActivationControl",
    "StaticRuntimeIdentityProvider",
    "UtcSystemClock",
    "build_authenticated_staging_lab_verifier",
]
