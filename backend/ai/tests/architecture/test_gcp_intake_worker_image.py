from pathlib import Path

AI_ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = AI_ROOT / "ops" / "gcp-intake-worker" / "Dockerfile"


def test_worker_image_is_digest_pinned_and_drops_build_tools() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")

    assert dockerfile.count("FROM python:3.14.6-slim-trixie@sha256:") == 1
    assert (
        "FROM cgr.dev/chainguard/python:latest@sha256:" in dockerfile
    )
    assert " AS builder" in dockerfile
    assert "COPY --from=builder /opt/vfbiz/.venv ./.venv" in dockerfile

    runtime_stage = dockerfile.split(
        "FROM cgr.dev/chainguard/python:latest@sha256:", maxsplit=1
    )[1]
    assert "COPY --from=uv" not in runtime_stage
    assert "uv sync" not in runtime_stage
    assert "USER 65532:65532" in runtime_stage
    assert 'ENTRYPOINT ["/usr/bin/python3.14"]' in runtime_stage


def test_worker_image_has_no_mutable_package_install_step() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")

    assert "apt-get" not in dockerfile
    assert "pip install" not in dockerfile
    assert "@sha256:" in dockerfile
