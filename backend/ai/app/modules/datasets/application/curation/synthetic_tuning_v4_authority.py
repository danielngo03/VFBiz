from __future__ import annotations

from app.modules.datasets.application.curation.synthetic_tuning_candidate import (
    TrustedCandidateAuthority,
)

VIVI_BEHAVIOR_SYNTHETIC_V4_AUTHORITY = TrustedCandidateAuthority(
    candidate_id="vivi-behavior-synthetic-v4",
    work_item="VFBIZ-0214",
    source="synthetic",
    verifier_revision="synthetic-tuning-candidate-v2",
    verifier_source_path=(
        "backend/ai/app/modules/datasets/application/curation/synthetic_tuning_candidate.py"
    ),
    verifier_source_sha256=("c3d7dedbcb2d238c4b13b5378b8834ae9130abb02ae5ec371c82cba0561b3251"),
    text_quality_source_path=(
        "backend/ai/app/modules/datasets/application/curation/synthetic_text_quality.py"
    ),
    text_quality_source_sha256=(
        "f187a323652e466991d0be21a15a98d2ff04330dacf1508b9685fa14e577af9f"
    ),
    store_source_path=(
        "backend/ai/app/modules/datasets/infrastructure/synthetic_tuning_candidate_store.py"
    ),
    store_source_sha256=("f8cc6310bd4781b0a5115a8bab3f9f984f8c92f8b376cdb32bcb9adb9fbc211b"),
    voice_rubric_source_path=(
        "backend/ai/dataset-specs/evaluation/rubrics/vivi-text-voice-v1.json"
    ),
    voice_rubric_file_sha256=("41d85114c6aaac140f351560cd852d072be14ccb5e5612e575b08f7eb8ce3e37"),
    voice_rubric_semantic_sha256=(
        "548051aab2d5f019693c0a45d94dfc421296300555de5ea1e424a4807c9e9f2d"
    ),
    domain_pack_source_path=(
        "backend/ai/dataset-specs/evaluation/voice/vivi-text-domain-pack-v1.json"
    ),
    domain_pack_file_sha256=("fc9d779292c4d75b18af6d7d27dfb8a1f95e32da467e94eec2e29e447d4ad415"),
    domain_pack_semantic_sha256=(
        "23b16f3cf148f456c8ffd8c510fa7e44352e56baf7925b17b6b727b856414b57"
    ),
    generator_identity="vfbiz-synthetic-behavior-composer@4.0.0",
    generator_source_path=(
        "backend/ai/app/modules/datasets/application/curation/synthetic_tuning_v4_generator.py"
    ),
    generator_source_sha256=("49fc6a70754855ba479aec238ce31deaba62bb7dc4d776b2ce93e71162863050"),
    seed_set_id="synthetic-behavior-seeds-v4",
    pinned_revisions_sha256=("77c19200d200152fa24df97fedc3048b94bf73d61822544581918f5f8afa541b"),
    family_lock_sha256=("2f889cefead518c21703bf93ea7c770cae69467b586b0d24dd64e3d81d40f68b"),
    scenario_lock_sha256=("2f889cefead518c21703bf93ea7c770cae69467b586b0d24dd64e3d81d40f68b"),
    behavior_labels_sha256=("f20d638a6fcf94df6adf9900adcdad436f6561b6850dabc89795759be2968451"),
    governance_metadata_sha256=("c7f5eef9a97c46827306f610e99731c2024ef6d6e53570a80e9cf3b86779836e"),
    regression_source_bindings=(
        (
            "vivi-behavior-synthetic-v2-fam-05-21-v5",
            "0d81fbb247294d66dfb4b7a080eb228905278247a74acf121af628c26db6c575",
            20,
        ),
        (
            "vivi-behavior-synthetic-v2-fam-05-22-v5",
            "4e267af43f69b4a482e468b5190cc25c282fb7f5d419c7b2f1b944d8e83ef62d",
            20,
        ),
        (
            "vivi-behavior-synthetic-v2-fam-05-23-v5",
            "76e1b4bd3db6500259a3b398005cb9d6180923bd8737e105204afd3a178c5840",
            20,
        ),
        (
            "vivi-behavior-synthetic-v2-fam-05-24-v5",
            "234b26a33c16a6458c002f53aa9c916910604980499d1df3dbd82295c0e80d2a",
            22,
        ),
    ),
    allowed_exports=("gemini/train.jsonl", "gemini/validation.jsonl"),
    expected_record_count=625,
    expected_split_counts={"train": 400, "validation": 100, "test": 125},
)
