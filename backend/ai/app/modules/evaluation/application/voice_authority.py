from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, cast


class VoiceAuthorityError(ValueError):
    """Raised when a voice evaluation artifact is unknown, mutable, or mismatched."""


_TRUSTED_ARTIFACT_SHA256 = {
    "customer-assistant-golden-v1-candidate.json": (
        "ef748537dbebc0ae787c84e859cb1755fca864544501d37c823374058962c2a6"
    ),
    "vivi-text-voice-v1.json": "41d85114c6aaac140f351560cd852d072be14ccb5e5612e575b08f7eb8ce3e37",
    "vivi-text-domain-pack-v1.json": (
        "fc9d779292c4d75b18af6d7d27dfb8a1f95e32da467e94eec2e29e447d4ad415"
    ),
    "vivi-text-board-policy-v1.json": (
        "3f98556a6fcbab836d32e42c6081cc0c3235a42ee444075bc75f41ce9f2c33b3"
    ),
    "vivi-text-calibration-plan-v1.json": (
        "be96a99c34efb13c43cc26175e1093429bb2f03dea48568109377652a942cf90"
    ),
    "vivi-text-heldout-plan-v1.json": (
        "f880335c4d243f5d67a3f7c35eeed06f1b1f6704da2954062e760b238aafb9d0"
    ),
}


def _canonical_digest(payload: Mapping[str, Any], digest_field: str) -> str:
    basis = {key: value for key, value in payload.items() if key != digest_field}
    canonical = json.dumps(
        basis,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _read_digest_bound(path: Path, *, digest_field: str) -> Mapping[str, Any]:
    try:
        payload = path.read_bytes()
        value = json.loads(payload)
    except (OSError, json.JSONDecodeError) as error:
        raise VoiceAuthorityError(f"voice artifact is unavailable: {path.name}") from error
    if not isinstance(value, dict):
        raise VoiceAuthorityError(f"voice artifact must be an object: {path.name}")
    value = cast(dict[str, Any], value)
    observed = value.get(digest_field)
    if not isinstance(observed, str) or observed != _canonical_digest(value, digest_field):
        raise VoiceAuthorityError(f"voice artifact digest mismatch: {path.name}")
    if hashlib.sha256(payload).hexdigest() != _TRUSTED_ARTIFACT_SHA256.get(path.name):
        raise VoiceAuthorityError(f"voice artifact is not trusted: {path.name}")
    return MappingProxyType(value)


@dataclass(frozen=True, slots=True)
class ViViTextVoiceAuthority:
    suite: Mapping[str, Any]
    rubric: Mapping[str, Any]
    domain_pack: Mapping[str, Any]
    board_policy: Mapping[str, Any]
    calibration_plan: Mapping[str, Any]
    heldout_plan: Mapping[str, Any]

    @classmethod
    def load(cls, specification_root: Path) -> ViViTextVoiceAuthority:
        suite = _read_digest_bound(
            specification_root / "suites" / "customer-assistant-golden-v1-candidate.json",
            digest_field="voice_suite_semantic_digest",
        )
        rubric = _read_digest_bound(
            specification_root / "rubrics" / "vivi-text-voice-v1.json",
            digest_field="semantic_digest",
        )
        voice_root = specification_root / "voice"
        domain_pack = _read_digest_bound(
            voice_root / "vivi-text-domain-pack-v1.json",
            digest_field="semantic_digest",
        )
        board_policy = _read_digest_bound(
            voice_root / "vivi-text-board-policy-v1.json",
            digest_field="semantic_digest",
        )
        calibration_plan = _read_digest_bound(
            voice_root / "vivi-text-calibration-plan-v1.json",
            digest_field="semantic_digest",
        )
        heldout_plan = _read_digest_bound(
            voice_root / "vivi-text-heldout-plan-v1.json",
            digest_field="semantic_digest",
        )
        bindings = {
            "voice_profile_revision": rubric.get("rubric_id"),
            "voice_domain_pack_revision": domain_pack.get("domain_pack_id"),
            "voice_board_policy_revision": board_policy.get("board_policy_id"),
            "voice_calibration_plan_revision": calibration_plan.get("calibration_plan_id"),
            "voice_heldout_plan_revision": heldout_plan.get("heldout_plan_id"),
        }
        for suite_field, artifact_revision in bindings.items():
            if suite.get(suite_field) != artifact_revision:
                raise VoiceAuthorityError(f"voice revision mismatch: {suite_field}")
        return cls(
            suite=suite,
            rubric=rubric,
            domain_pack=domain_pack,
            board_policy=board_policy,
            calibration_plan=calibration_plan,
            heldout_plan=heldout_plan,
        )

    @property
    def voice_profile_revision(self) -> str:
        return str(self.suite["voice_profile_revision"])

    def assert_case_revision(self, rubric_revision: str) -> None:
        if rubric_revision != self.voice_profile_revision:
            raise VoiceAuthorityError("evaluation case uses an unknown voice revision")

    @property
    def release_blocked(self) -> bool:
        return any(
            artifact.get("status") == "human-blocked"
            for artifact in (
                self.suite,
                self.board_policy,
                self.calibration_plan,
                self.heldout_plan,
            )
        )
