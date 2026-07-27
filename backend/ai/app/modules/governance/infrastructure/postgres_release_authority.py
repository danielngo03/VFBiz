import asyncio
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol, cast
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.governance.application.release_resolver import (
    ArtifactDigestReader,
    ReleaseEvidenceVerifier,
    ReleaseManifestResolutionError,
    ReleaseManifestResolver,
    ReleaseManifestStore,
)
from app.modules.governance.domain.release_authority import (
    AssistantReleaseAuthorityTransaction,
    ReleaseAuthoritySchemaValidator,
)
from app.modules.governance.domain.release_manifest import (
    ApprovalEvidence,
    AssistantReleaseArtifacts,
    AssistantReleaseCandidate,
    AssistantReleaseManifest,
    AutomatedGateEvidence,
    PriorActivationRollbackTarget,
    PromotionEvidence,
    ReleaseActivationState,
    StaticSafeApprovalEvidence,
    StaticSafeRelease,
    StaticSafeReleaseRollbackTarget,
)

_ACTIVE_HISTORY_EVENTS = frozenset({"activated", "superseded", "rolled_back"})


class ReleasePersistenceErrorCode(StrEnum):
    DATABASE_UNAVAILABLE = "RELEASE_DATABASE_UNAVAILABLE"
    SNAPSHOT_INVALID = "RELEASE_SNAPSHOT_INVALID"
    CANONICAL_DOCUMENT_INVALID = "RELEASE_CANONICAL_DOCUMENT_INVALID"
    ROLLBACK_HISTORY_INVALID = "ROLLBACK_HISTORY_INVALID"
    ROLLBACK_CYCLE = "ROLLBACK_CYCLE"
    RESOLUTION_TIMEOUT = "RELEASE_RESOLUTION_TIMEOUT"
    CONCURRENCY_LIMIT = "RELEASE_RESOLUTION_CONCURRENCY_LIMIT"
    AUTHORITY_CHANGED = "RELEASE_AUTHORITY_CHANGED"
    HISTORY_LIMIT_EXCEEDED = "RELEASE_HISTORY_LIMIT_EXCEEDED"


class ReleasePersistenceError(RuntimeError):
    def __init__(
        self,
        code: ReleasePersistenceErrorCode,
        *,
        retryable: bool,
    ) -> None:
        super().__init__(code.value)
        self.code = code
        self.retryable = retryable


class TrustFreshnessFence(Protocol):
    def begin_freshness_scope(self) -> object: ...

    async def assert_fresh(self) -> None: ...

    def end_freshness_scope(self, token: object) -> None: ...


@dataclass(frozen=True, slots=True)
class _ReleaseSnapshot:
    manifest: AssistantReleaseManifest
    manifests: Mapping[str, AssistantReleaseManifest]
    freshness: "_PointerFreshness"


@dataclass(frozen=True, slots=True)
class _PointerFreshness:
    assistant_profile: str
    environment: str
    target_kind: str
    activation_record_id: UUID | None
    static_safe_record_id: UUID | None
    revision: int
    history_head_sha256: str


class _SnapshotStore(ReleaseManifestStore):
    def __init__(self, snapshot: _ReleaseSnapshot) -> None:
        self._snapshot = snapshot

    async def get(self, activation_id: str) -> AssistantReleaseManifest | None:
        return self._snapshot.manifests.get(activation_id)

    async def get_candidate(
        self,
        candidate_id: str,
    ) -> AssistantReleaseCandidate | None:
        return next(
            (
                manifest.candidate
                for manifest in self._snapshot.manifests.values()
                if manifest.candidate.candidate_id == candidate_id
            ),
            None,
        )


class PostgresReleaseAuthorityResolver:
    """Resolve one immutable release from one repeatable-read PostgreSQL snapshot."""

    def __init__(
        self,
        *,
        sessions: async_sessionmaker[AsyncSession],
        digest_reader: ArtifactDigestReader,
        evidence_verifier: ReleaseEvidenceVerifier,
        schema_validator: ReleaseAuthoritySchemaValidator,
        required_approval_roles: tuple[str, ...],
        clock: Callable[[], datetime],
        trust_freshness_fence: TrustFreshnessFence,
        timeout_seconds: float = 10,
        max_concurrency: int = 16,
        acquire_timeout_seconds: float = 1,
        max_history_events: int = 4096,
    ) -> None:
        if (
            timeout_seconds <= 0
            or max_concurrency <= 0
            or acquire_timeout_seconds <= 0
            or max_history_events <= 0
        ):
            raise ValueError("release resolver limits must be positive")
        self._sessions = sessions
        self._digest_reader = digest_reader
        self._evidence_verifier = evidence_verifier
        self._schema_validator = schema_validator
        self._required_approval_roles = required_approval_roles
        self._clock = clock
        self._timeout_seconds = timeout_seconds
        self._acquire_timeout_seconds = acquire_timeout_seconds
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._max_history_events = max_history_events
        self._trust_freshness_fence = trust_freshness_fence

    async def resolve(
        self,
        *,
        activation_id: str,
        expected_candidate_sha256: str,
        assistant_profile: str,
        environment: str,
    ) -> AssistantReleaseManifest:
        acquired = False
        try:
            async with asyncio.timeout(self._acquire_timeout_seconds):
                await self._semaphore.acquire()
                acquired = True
        except TimeoutError as error:
            raise ReleasePersistenceError(
                ReleasePersistenceErrorCode.CONCURRENCY_LIMIT,
                retryable=True,
            ) from error
        try:
            async with asyncio.timeout(self._timeout_seconds):
                trust_token = self._trust_freshness_fence.begin_freshness_scope()
                try:
                    snapshot = await self._read_snapshot(
                        activation_id=activation_id,
                        assistant_profile=assistant_profile,
                        environment=environment,
                    )
                    resolver = ReleaseManifestResolver(
                        store=_SnapshotStore(snapshot),
                        digest_reader=self._digest_reader,
                        evidence_verifier=self._evidence_verifier,
                        required_approval_roles=self._required_approval_roles,
                        clock=self._clock,
                    )
                    resolved = await resolver.resolve(
                        activation_id=activation_id,
                        expected_candidate_sha256=expected_candidate_sha256,
                        assistant_profile=assistant_profile,
                        environment=environment,
                    )
                    await self._assert_fresh(snapshot.freshness)
                    await self._trust_freshness_fence.assert_fresh()
                    return resolved
                finally:
                    self._trust_freshness_fence.end_freshness_scope(trust_token)
        except TimeoutError as error:
            raise ReleasePersistenceError(
                ReleasePersistenceErrorCode.RESOLUTION_TIMEOUT,
                retryable=True,
            ) from error
        except asyncio.CancelledError:
            raise
        finally:
            if acquired:
                self._semaphore.release()

    async def _read_snapshot(
        self,
        *,
        activation_id: str,
        assistant_profile: str,
        environment: str,
    ) -> _ReleaseSnapshot:
        try:
            async with self._sessions() as session, session.begin():
                await session.execute(
                    text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                )
                return await _load_snapshot(
                    session,
                    activation_id=activation_id,
                    assistant_profile=assistant_profile,
                    environment=environment,
                    schema_validator=self._schema_validator,
                    max_history_events=self._max_history_events,
                )
        except asyncio.CancelledError:
            raise
        except ReleasePersistenceError:
            raise
        except SQLAlchemyError as error:
            raise ReleasePersistenceError(
                ReleasePersistenceErrorCode.DATABASE_UNAVAILABLE,
                retryable=True,
            ) from error
        except (KeyError, TypeError, ValueError) as error:
            raise ReleasePersistenceError(
                ReleasePersistenceErrorCode.CANONICAL_DOCUMENT_INVALID,
                retryable=False,
            ) from error

    async def _assert_fresh(self, expected: _PointerFreshness) -> None:
        try:
            async with self._sessions() as session:
                observed = (
                    (
                        await session.execute(
                            text(
                                """
                                SELECT target_kind, activation_record_id,
                                       static_safe_release_record_id, revision,
                                       last_history_event_sha256
                                FROM ai_assistant_release_pointer
                                WHERE assistant_profile = :assistant_profile
                                  AND environment = :environment
                                """
                            ),
                            {
                                "assistant_profile": expected.assistant_profile,
                                "environment": expected.environment,
                            },
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
        except asyncio.CancelledError:
            raise
        except SQLAlchemyError as error:
            raise ReleasePersistenceError(
                ReleasePersistenceErrorCode.DATABASE_UNAVAILABLE,
                retryable=True,
            ) from error
        if observed is None or (
            observed["target_kind"],
            observed["activation_record_id"],
            observed["static_safe_release_record_id"],
            int(observed["revision"]),
            observed["last_history_event_sha256"],
        ) != (
            expected.target_kind,
            expected.activation_record_id,
            expected.static_safe_record_id,
            expected.revision,
            expected.history_head_sha256,
        ):
            raise ReleasePersistenceError(
                ReleasePersistenceErrorCode.AUTHORITY_CHANGED,
                retryable=True,
            )


async def _load_snapshot(
    session: AsyncSession,
    *,
    activation_id: str,
    assistant_profile: str,
    environment: str,
    schema_validator: ReleaseAuthoritySchemaValidator,
    max_history_events: int,
) -> _ReleaseSnapshot:
    raw_row = (
        (
            await session.execute(
                text(
                    """
                SELECT
                  activation.id AS activation_record_id,
                  activation.activation_id,
                  activation.assistant_profile,
                  activation.environment,
                  activation.candidate_sha256,
                  activation.approval_set_sha256,
                  activation.automated_gate_evidence_sha256,
                  activation.activation_core_sha256,
                  activation.activation_envelope_sha256,
                  activation.effective_at,
                  activation.expires_at,
                  activation.rollback_target_kind,
                  activation.rollback_activation_record_id,
                  activation.rollback_static_safe_record_id,
                  activation.kill_switch_registry_ref,
                  activation.kill_switch_registry_sha256,
                  activation.rollback_drill_evidence_ref,
                  activation.rollback_drill_evidence_sha256,
                  activation.promotion_evidence_ref,
                  activation.promotion_evidence_sha256,
                  activation.canonical_document AS activation_document,
                  candidate.id AS candidate_record_id,
                  candidate.candidate_id,
                  candidate.content_sha256,
                  candidate.requested_by_subject,
                  candidate.gate_policy_revision,
                  candidate.gate_policy_sha256,
                  candidate.canonical_document AS candidate_document,
                  static_safe.id AS static_safe_record_id,
                  static_safe.safe_release_core_sha256,
                  static_safe.approval_set_sha256
                    AS static_safe_approval_set_sha256,
                  static_safe.safe_release_envelope_sha256,
                  static_safe.canonical_document AS static_safe_document,
                  pointer.target_kind AS pointer_target_kind,
                  pointer.activation_record_id AS pointer_activation_record_id,
                  pointer.static_safe_release_record_id
                    AS pointer_static_safe_record_id,
                  pointer.revision AS pointer_revision,
                  pointer.last_history_event_sha256
                FROM ai_assistant_release_activation activation
                JOIN ai_assistant_release_candidate candidate
                  ON candidate.id = activation.candidate_record_id
                JOIN ai_assistant_static_safe_release static_safe
                  ON static_safe.id = activation.static_safe_release_record_id
                 AND static_safe.assistant_profile = activation.assistant_profile
                 AND static_safe.environment = activation.environment
                LEFT JOIN ai_assistant_release_pointer pointer
                  ON pointer.assistant_profile = activation.assistant_profile
                 AND pointer.environment = activation.environment
                WHERE activation.activation_id = :activation_id
                  AND activation.assistant_profile = :assistant_profile
                  AND activation.environment = :environment
                """
                ),
                {
                    "activation_id": activation_id,
                    "assistant_profile": assistant_profile,
                    "environment": environment,
                },
            )
        )
        .mappings()
        .one_or_none()
    )
    if raw_row is None:
        # Do not reveal whether the activation exists under another scope.
        raise ReleaseManifestResolutionError("RELEASE_NOT_FOUND")
    row = cast(Mapping[str, Any], dict(raw_row))
    if row["pointer_revision"] is None:
        raise ReleasePersistenceError(
            ReleasePersistenceErrorCode.SNAPSHOT_INVALID,
            retryable=False,
        )

    raw_history = (
        (
            await session.execute(
                text(
                    """
                SELECT id, sequence, event_type, pointer_revision,
                       from_activation_record_id, from_static_safe_record_id,
                       to_activation_record_id, to_static_safe_record_id,
                       history_event_ref, previous_event_sha256, event_sha256,
                       canonical_document
                FROM ai_assistant_release_history
                WHERE assistant_profile = :assistant_profile
                  AND environment = :environment
                ORDER BY sequence
                LIMIT :history_fetch_limit
                """
                ),
                {
                    "assistant_profile": assistant_profile,
                    "environment": environment,
                    "history_fetch_limit": max_history_events + 1,
                },
            )
        )
        .mappings()
        .all()
    )
    history = [cast(Mapping[str, Any], dict(item)) for item in raw_history]
    if len(history) > max_history_events:
        raise ReleasePersistenceError(
            ReleasePersistenceErrorCode.HISTORY_LIMIT_EXCEEDED,
            retryable=False,
        )
    _validate_history_chain(row, history)

    activation_document = AssistantReleaseAuthorityTransaction(
        _as_mapping(row["activation_document"], "activation document"),
        schema_validator=schema_validator,
    ).to_document()
    candidate_document = _as_mapping(row["candidate_document"], "candidate document")
    candidate_payload = _as_mapping(activation_document["candidate"], "candidate")
    if candidate_payload != candidate_document:
        raise ReleasePersistenceError(
            ReleasePersistenceErrorCode.CANONICAL_DOCUMENT_INVALID,
            retryable=False,
        )
    candidate = _candidate(candidate_payload)
    _validate_candidate_row(row, candidate)
    static_safe_document = _as_mapping(
        activation_document["static_safe_release"],
        "static-safe release",
    )
    if static_safe_document != _as_mapping(
        row["static_safe_document"],
        "persisted static-safe release",
    ):
        raise ReleasePersistenceError(
            ReleasePersistenceErrorCode.CANONICAL_DOCUMENT_INVALID,
            retryable=False,
        )
    state = _activation_state(row, history)

    rollback_document = _as_mapping(
        activation_document["rollback_target"],
        "rollback target",
    )
    manifests: dict[str, AssistantReleaseManifest] = {}
    if rollback_document["kind"] == "prior_activation":
        target, rollback_manifest = await _prior_activation_target(
            session,
            row=row,
            history=history,
            document=rollback_document,
            schema_validator=schema_validator,
        )
        manifests[rollback_manifest.activation_id] = rollback_manifest
        static_safe = _static_safe(static_safe_document)
    elif rollback_document["kind"] == "static_safe_release":
        target = _static_safe_target(rollback_document)
        static_safe = _static_safe(static_safe_document)
        if (
            row["rollback_target_kind"] != "static_safe_release"
            or row["rollback_static_safe_record_id"] is None
            or target != static_safe.rollback_target()
        ):
            raise ReleasePersistenceError(
                ReleasePersistenceErrorCode.ROLLBACK_HISTORY_INVALID,
                retryable=False,
            )
    else:
        raise ValueError("unsupported rollback target kind")

    manifest = _manifest(
        activation_document,
        candidate=candidate,
        state=state,
        rollback_target=target,
        static_safe=static_safe,
    )
    manifests[manifest.activation_id] = manifest
    _validate_activation_row(row, manifest)
    freshness = _PointerFreshness(
        assistant_profile=str(row["assistant_profile"]),
        environment=str(row["environment"]),
        target_kind=str(row["pointer_target_kind"]),
        activation_record_id=cast(UUID | None, row["pointer_activation_record_id"]),
        static_safe_record_id=cast(UUID | None, row["pointer_static_safe_record_id"]),
        revision=int(row["pointer_revision"]),
        history_head_sha256=str(row["last_history_event_sha256"]),
    )
    return _ReleaseSnapshot(
        manifest=manifest,
        manifests=manifests,
        freshness=freshness,
    )


def _manifest(
    activation_document: Mapping[str, Any],
    *,
    candidate: AssistantReleaseCandidate,
    state: ReleaseActivationState,
    rollback_target: PriorActivationRollbackTarget | StaticSafeReleaseRollbackTarget,
    static_safe: StaticSafeRelease,
) -> AssistantReleaseManifest:
    return AssistantReleaseManifest(
        activation_id=str(activation_document["activation_id"]),
        candidate=candidate,
        state=state,
        automated_gate=_automated_gate(
            _as_mapping(activation_document["automated_gate"], "automated gate")
        ),
        approvals=tuple(
            _approval(_as_mapping(item, "approval"))
            for item in _as_list(activation_document["approvals"], "approvals")
        ),
        effective_at=_timestamp(activation_document["effective_at"], "effective_at"),
        expires_at=_timestamp(activation_document["expires_at"], "expires_at"),
        kill_switch_registry_ref=str(activation_document["kill_switch_registry_ref"]),
        kill_switch_registry_sha256=str(activation_document["kill_switch_registry_sha256"]),
        rollback_drill_evidence_ref=str(activation_document["rollback_drill_evidence_ref"]),
        rollback_drill_evidence_sha256=str(activation_document["rollback_drill_evidence_sha256"]),
        activation_core_sha256=str(activation_document["activation_core_sha256"]),
        activation_envelope_sha256=str(activation_document["activation_envelope_sha256"]),
        promotion_evidence=PromotionEvidence(
            evidence_ref=str(activation_document["promotion_evidence_ref"]),
            evidence_sha256=str(activation_document["promotion_evidence_sha256"]),
            target_activation_core_sha256=str(
                activation_document["promotion_evidence_target_sha256"]
            ),
        ),
        rollback_target=rollback_target,
        static_safe_release=static_safe,
    )


def _validate_history_chain(
    activation_row: Mapping[str, Any],
    history: list[Mapping[str, Any]],
) -> None:
    pointer_revision = int(activation_row["pointer_revision"])
    if not history or pointer_revision != len(history):
        raise ReleasePersistenceError(
            ReleasePersistenceErrorCode.SNAPSHOT_INVALID,
            retryable=False,
        )
    prior: str | None = None
    for expected_sequence, event in enumerate(history, start=1):
        if (
            int(event["sequence"]) != expected_sequence
            or int(event["pointer_revision"]) != expected_sequence
            or event["previous_event_sha256"] != prior
        ):
            raise ReleasePersistenceError(
                ReleasePersistenceErrorCode.SNAPSHOT_INVALID,
                retryable=False,
            )
        prior = str(event["event_sha256"])
    if activation_row["last_history_event_sha256"] != prior:
        raise ReleasePersistenceError(
            ReleasePersistenceErrorCode.SNAPSHOT_INVALID,
            retryable=False,
        )


def _activation_state(
    activation_row: Mapping[str, Any],
    history: list[Mapping[str, Any]],
) -> ReleaseActivationState:
    record_id = activation_row["activation_record_id"]
    if (
        activation_row["pointer_target_kind"] == "activation"
        and activation_row["pointer_activation_record_id"] == record_id
    ):
        latest = history[-1]
        if latest["to_activation_record_id"] != record_id:
            raise ReleasePersistenceError(
                ReleasePersistenceErrorCode.SNAPSHOT_INVALID,
                retryable=False,
            )
        return ReleaseActivationState.ACTIVE
    related = [
        event
        for event in history
        if event["from_activation_record_id"] == record_id
        or event["to_activation_record_id"] == record_id
    ]
    if not related or related[-1]["from_activation_record_id"] != record_id:
        raise ReleasePersistenceError(
            ReleasePersistenceErrorCode.SNAPSHOT_INVALID,
            retryable=False,
        )
    if related[-1]["event_type"] == "revoked":
        return ReleaseActivationState.REVOKED
    return ReleaseActivationState.SUPERSEDED


async def _prior_activation_target(
    session: AsyncSession,
    *,
    row: Mapping[str, Any],
    history: list[Mapping[str, Any]],
    document: Mapping[str, Any],
    schema_validator: ReleaseAuthoritySchemaValidator,
) -> tuple[PriorActivationRollbackTarget, AssistantReleaseManifest]:
    rollback_record_id = row["rollback_activation_record_id"]
    if row["rollback_target_kind"] != "prior_activation" or not isinstance(
        rollback_record_id, UUID
    ):
        raise ReleasePersistenceError(
            ReleasePersistenceErrorCode.ROLLBACK_HISTORY_INVALID,
            retryable=False,
        )
    rollback = (
        (
            await session.execute(
                text(
                    """
                SELECT activation.id AS activation_record_id,
                       activation.activation_id,
                       activation.activation_envelope_sha256,
                       activation.canonical_document AS activation_document,
                       candidate.candidate_id, candidate.content_sha256,
                       candidate.canonical_document AS candidate_document,
                       static_safe.canonical_document AS static_safe_document
                FROM ai_assistant_release_activation activation
                JOIN ai_assistant_release_candidate candidate
                  ON candidate.id = activation.candidate_record_id
                JOIN ai_assistant_static_safe_release static_safe
                  ON static_safe.id = activation.static_safe_release_record_id
                 AND static_safe.assistant_profile = activation.assistant_profile
                 AND static_safe.environment = activation.environment
                WHERE activation.id = :record_id
                  AND activation.assistant_profile = :assistant_profile
                  AND activation.environment = :environment
                """
                ),
                {
                    "record_id": rollback_record_id,
                    "assistant_profile": row["assistant_profile"],
                    "environment": row["environment"],
                },
            )
        )
        .mappings()
        .one_or_none()
    )
    if rollback is None:
        raise ReleasePersistenceError(
            ReleasePersistenceErrorCode.ROLLBACK_HISTORY_INVALID,
            retryable=False,
        )
    rollback_document = AssistantReleaseAuthorityTransaction(
        _as_mapping(rollback["activation_document"], "rollback activation"),
        schema_validator=schema_validator,
    ).to_document()
    rollback_candidate_document = _as_mapping(
        rollback["candidate_document"],
        "rollback candidate",
    )
    embedded_candidate_document = _as_mapping(
        rollback_document["candidate"],
        "rollback embedded candidate",
    )
    if rollback_candidate_document != embedded_candidate_document:
        raise ReleasePersistenceError(
            ReleasePersistenceErrorCode.CANONICAL_DOCUMENT_INVALID,
            retryable=False,
        )
    embedded_static_safe_document = _as_mapping(
        rollback_document["static_safe_release"],
        "prior embedded static-safe release",
    )
    if embedded_static_safe_document != _as_mapping(
        rollback["static_safe_document"],
        "prior persisted static-safe release",
    ):
        raise ReleasePersistenceError(
            ReleasePersistenceErrorCode.CANONICAL_DOCUMENT_INVALID,
            retryable=False,
        )
    candidate = _candidate(embedded_candidate_document)
    target = _prior_target(document)
    if (
        target.activation_id != rollback["activation_id"]
        or target.activation_envelope_sha256 != rollback["activation_envelope_sha256"]
        or target.candidate_id != candidate.candidate_id
        or target.candidate_sha256 != candidate.content_sha256
    ):
        raise ReleasePersistenceError(
            ReleasePersistenceErrorCode.ROLLBACK_HISTORY_INVALID,
            retryable=False,
        )
    eligible = next(
        (
            event
            for event in history
            if event["history_event_ref"] == target.eligible_history_event_ref
            and event["event_sha256"] == target.eligible_history_event_sha256
            and event["to_activation_record_id"] == rollback_record_id
            and event["event_type"] in _ACTIVE_HISTORY_EVENTS
        ),
        None,
    )
    current_first_sequence = min(
        int(event["sequence"])
        for event in history
        if event["to_activation_record_id"] == row["activation_record_id"]
    )
    if eligible is None or int(eligible["sequence"]) >= current_first_sequence:
        raise ReleasePersistenceError(
            ReleasePersistenceErrorCode.ROLLBACK_HISTORY_INVALID,
            retryable=False,
        )
    cycle, truncated = (
        await session.execute(
            text(
                """
                WITH RECURSIVE chain AS (
                  SELECT id, rollback_activation_record_id, ARRAY[id] AS path,
                         false AS cycle, 1 AS depth
                  FROM ai_assistant_release_activation
                  WHERE id = :record_id
                  UNION ALL
                  SELECT next.id, next.rollback_activation_record_id,
                         chain.path || next.id,
                         next.id = ANY(chain.path),
                         chain.depth + 1
                  FROM chain
                  JOIN ai_assistant_release_activation next
                    ON next.id = chain.rollback_activation_record_id
                   AND next.assistant_profile = :assistant_profile
                   AND next.environment = :environment
                  WHERE NOT chain.cycle AND chain.depth < 64
                )
                SELECT coalesce(bool_or(cycle), false),
                       coalesce(bool_or(
                         depth = 64 AND rollback_activation_record_id IS NOT NULL
                       ), false)
                FROM chain
                """
            ),
            {
                "record_id": row["activation_record_id"],
                "assistant_profile": row["assistant_profile"],
                "environment": row["environment"],
            },
        )
    ).one()
    if bool(cycle) or bool(truncated):
        raise ReleasePersistenceError(
            ReleasePersistenceErrorCode.ROLLBACK_CYCLE,
            retryable=False,
        )
    prior_rollback_document = _as_mapping(
        rollback_document["rollback_target"],
        "prior rollback target",
    )
    prior_target = (
        _prior_target(prior_rollback_document)
        if prior_rollback_document["kind"] == "prior_activation"
        else _static_safe_target(prior_rollback_document)
    )
    prior_state_row = dict(row)
    prior_state_row["activation_record_id"] = rollback_record_id
    manifest = _manifest(
        rollback_document,
        candidate=candidate,
        state=_activation_state(prior_state_row, history),
        rollback_target=prior_target,
        static_safe=_static_safe(embedded_static_safe_document),
    )
    return target, manifest


def _candidate(document: Mapping[str, Any]) -> AssistantReleaseCandidate:
    artifacts = _as_mapping(document["artifacts"], "candidate artifacts")
    datasets = tuple(
        _as_mapping(item, "dataset release")
        for item in _as_list(artifacts["dataset_releases"], "dataset releases")
    )
    value = AssistantReleaseCandidate(
        candidate_id=str(document["candidate_id"]),
        assistant_profile=str(document["assistant_profile"]),
        environment=str(document["environment"]),
        requested_by_subject=str(document["requested_by_subject"]),
        gate_policy_revision=str(document["gate_policy_revision"]),
        gate_policy_sha256=str(document["gate_policy_sha256"]),
        artifacts=AssistantReleaseArtifacts(
            model_deployment_ref=_artifact_ref(artifacts, "model_deployment"),
            model_deployment_sha256=_artifact_digest(artifacts, "model_deployment"),
            prompt_ref=_artifact_ref(artifacts, "prompt"),
            prompt_sha256=_artifact_digest(artifacts, "prompt"),
            output_schema_ref=_artifact_ref(artifacts, "output_schema"),
            output_schema_sha256=_artifact_digest(artifacts, "output_schema"),
            graph_ref=_artifact_ref(artifacts, "graph"),
            graph_sha256=_artifact_digest(artifacts, "graph"),
            policy_ref=_artifact_ref(artifacts, "policy"),
            policy_sha256=_artifact_digest(artifacts, "policy"),
            validator_ref=_artifact_ref(artifacts, "validator"),
            validator_sha256=_artifact_digest(artifacts, "validator"),
            knowledge_profile_ref=_artifact_ref(artifacts, "knowledge_profile"),
            knowledge_profile_sha256=_artifact_digest(artifacts, "knowledge_profile"),
            retriever_ref=_artifact_ref(artifacts, "retriever"),
            retriever_sha256=_artifact_digest(artifacts, "retriever"),
            embedding_generation_digest=str(artifacts["embedding_generation_sha256"]),
            dataset_release_refs=tuple(str(item["ref"]) for item in datasets),
            dataset_release_sha256=tuple(str(item["sha256"]) for item in datasets),
            tool_registry_ref=_artifact_ref(artifacts, "tool_registry"),
            tool_registry_sha256=_artifact_digest(artifacts, "tool_registry"),
            evaluator_ref=_artifact_ref(artifacts, "evaluator"),
            evaluator_sha256=_artifact_digest(artifacts, "evaluator"),
        ),
    )
    if value.content_sha256 != document["content_sha256"]:
        raise ValueError("candidate canonical digest mismatch")
    return value


def _approval(document: Mapping[str, Any]) -> ApprovalEvidence:
    return ApprovalEvidence(
        approval_id=str(document["approval_id"]),
        authority_role=str(document["authority_role"]),
        approver_subject=str(document["approver_subject"]),
        approved_at=_timestamp(document["approved_at"], "approved_at"),
        evidence_ref=str(document["evidence_ref"]),
        evidence_sha256=str(document["evidence_sha256"]),
        target_candidate_sha256=str(document["target_candidate_sha256"]),
        assistant_profile=str(document["assistant_profile"]),
        environment=str(document["environment"]),
    )


def _automated_gate(document: Mapping[str, Any]) -> AutomatedGateEvidence:
    return AutomatedGateEvidence(
        evidence_ref=str(document["evidence_ref"]),
        evidence_sha256=str(document["evidence_sha256"]),
        target_candidate_sha256=str(document["target_candidate_sha256"]),
        assistant_profile=str(document["assistant_profile"]),
        environment=str(document["environment"]),
        gate_policy_revision=str(document["gate_policy_revision"]),
        gate_policy_sha256=str(document["gate_policy_sha256"]),
    )


def _static_safe(document: Mapping[str, Any]) -> StaticSafeRelease:
    return StaticSafeRelease(
        safe_release_id=str(document["safe_release_id"]),
        safe_release_ref=str(document["safe_release_ref"]),
        safe_release_core_sha256=str(document["safe_release_core_sha256"]),
        approval_set_sha256=str(document["approval_set_sha256"]),
        safe_release_envelope_sha256=str(document["safe_release_envelope_sha256"]),
        template_ref=str(document["template_ref"]),
        template_sha256=str(document["template_sha256"]),
        response_policy_ref=str(document["response_policy_ref"]),
        response_policy_sha256=str(document["response_policy_sha256"]),
        assistant_profile=str(document["assistant_profile"]),
        environment=str(document["environment"]),
        effective_at=_timestamp(document["effective_at"], "safe effective_at"),
        expires_at=_timestamp(document["expires_at"], "safe expires_at"),
        approvals=tuple(
            StaticSafeApprovalEvidence(
                approval_id=str(value["approval_id"]),
                authority_role=str(value["authority_role"]),
                approver_subject=str(value["approver_subject"]),
                approved_at=_timestamp(value["approved_at"], "safe approved_at"),
                evidence_ref=str(value["evidence_ref"]),
                evidence_sha256=str(value["evidence_sha256"]),
                target_safe_release_core_sha256=str(value["target_safe_release_core_sha256"]),
            )
            for value in (
                _as_mapping(item, "static-safe approval")
                for item in _as_list(document["approvals"], "safe approvals")
            )
        ),
    )


def _prior_target(document: Mapping[str, Any]) -> PriorActivationRollbackTarget:
    return PriorActivationRollbackTarget(
        activation_id=str(document["activation_id"]),
        activation_envelope_sha256=str(document["activation_envelope_sha256"]),
        candidate_id=str(document["candidate_id"]),
        candidate_sha256=str(document["candidate_sha256"]),
        assistant_profile=str(document["assistant_profile"]),
        environment=str(document["environment"]),
        eligible_history_event_ref=str(document["eligible_history_event_ref"]),
        eligible_history_event_sha256=str(document["eligible_history_event_sha256"]),
    )


def _static_safe_target(
    document: Mapping[str, Any],
) -> StaticSafeReleaseRollbackTarget:
    return StaticSafeReleaseRollbackTarget(
        safe_release_id=str(document["safe_release_id"]),
        safe_release_ref=str(document["safe_release_ref"]),
        safe_release_core_sha256=str(document["safe_release_core_sha256"]),
        approval_set_sha256=str(document["approval_set_sha256"]),
        safe_release_envelope_sha256=str(document["safe_release_envelope_sha256"]),
        assistant_profile=str(document["assistant_profile"]),
        environment=str(document["environment"]),
    )


def _validate_candidate_row(
    row: Mapping[str, Any],
    candidate: AssistantReleaseCandidate,
) -> None:
    if (
        row["candidate_id"] != candidate.candidate_id
        or row["content_sha256"] != candidate.content_sha256
        or row["candidate_sha256"] != candidate.content_sha256
        or row["requested_by_subject"] != candidate.requested_by_subject
        or row["gate_policy_revision"] != candidate.gate_policy_revision
        or row["gate_policy_sha256"] != candidate.gate_policy_sha256
        or row["assistant_profile"] != candidate.assistant_profile
        or row["environment"] != candidate.environment
    ):
        raise ValueError("candidate row and canonical document diverge")


def _validate_activation_row(
    row: Mapping[str, Any],
    manifest: AssistantReleaseManifest,
) -> None:
    static_safe = manifest.static_safe_release
    if static_safe is None:
        raise ValueError("persisted v3 manifest requires static-safe release")
    activation_document = _as_mapping(
        row["activation_document"],
        "activation document",
    )
    if (
        row["activation_id"] != manifest.activation_id
        or row["approval_set_sha256"] != activation_document["approval_set_sha256"]
        or row["automated_gate_evidence_sha256"] != manifest.automated_gate.evidence_sha256
        or row["activation_core_sha256"] != activation_document["activation_core_sha256"]
        or row["activation_envelope_sha256"] != activation_document["activation_envelope_sha256"]
        or row["safe_release_core_sha256"] != static_safe.safe_release_core_sha256
        or row["static_safe_approval_set_sha256"] != static_safe.approval_set_sha256
        or row["safe_release_envelope_sha256"] != static_safe.safe_release_envelope_sha256
        or row["effective_at"] != manifest.effective_at
        or row["expires_at"] != manifest.expires_at
        or row["kill_switch_registry_ref"] != manifest.kill_switch_registry_ref
        or row["kill_switch_registry_sha256"] != manifest.kill_switch_registry_sha256
        or row["rollback_drill_evidence_ref"] != manifest.rollback_drill_evidence_ref
        or row["rollback_drill_evidence_sha256"] != manifest.rollback_drill_evidence_sha256
        or row["promotion_evidence_ref"] != activation_document["promotion_evidence_ref"]
        or row["promotion_evidence_sha256"] != activation_document["promotion_evidence_sha256"]
    ):
        raise ValueError("activation row and canonical document diverge")


def _artifact_ref(artifacts: Mapping[str, Any], name: str) -> str:
    return str(_as_mapping(artifacts[name], name)["ref"])


def _artifact_digest(artifacts: Mapping[str, Any], name: str) -> str:
    return str(_as_mapping(artifacts[name], name)["sha256"])


def _timestamp(value: object, field: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        raise TypeError(f"{field} must be a timestamp")
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include timezone")
    return parsed


def _as_mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field} must be an object")
    return cast(Mapping[str, Any], value)


def _as_list(value: object, field: str) -> list[object]:
    if not isinstance(value, list):
        raise TypeError(f"{field} must be an array")
    return cast(list[object], value)
