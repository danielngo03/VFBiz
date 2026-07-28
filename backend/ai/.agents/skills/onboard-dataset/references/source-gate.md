# Source and download gate

Before network access, the Source Register entry must validate against
`contracts/ai/source-register.schema.json` at the fetch gate and contain:

- `status: fetch-approved` hoặc `purpose-approved`;
- pinned exact source revision, allowlisted HTTPS origin và Legal fetch evidence;
- commercial-use/access conditions, retention và deletion method;
- human `fetch_approval_evidence`.

Upstream checksum có thể chưa tồn tại. Sau fetch, Source Fetch Manifest phải ghi
observed SHA-256/tree hash, content-addressed quarantine path, media type/bytes
và scan evidence. Chỉ format JSON, JSONL, CSV hoặc Parquet được phép; không chạy
remote script hoặc `trust_remote_code`.

Trước parsing/evaluation, purpose gate còn yêu cầu một canonical Source Fetch
Manifest `scan-passed` được bind đúng source/revision/verified fetch ID,
`status: purpose-approved`,
requested purpose trong `approved_purposes` (và là subset của proposed), Data
Owner/custodian, derivative rights, ACL/classification cùng human
`purpose_approval_evidence`.

Gated access, click-through terms, conflicting license metadata, missing upstream
rights or non-commercial/no-derivatives terms are not “probably safe”. Keep the
entry at `legal-hold`/`rejected` and return `failed-safely`.

`scripts/fetch_to_quarantine.py` is the deterministic fetch boundary: it rejects
redirects, credentials in URLs, local/non-public IP literals, origin mismatch,
unsupported media types and oversized streams. It writes a content-addressed
artifact only; it never parses, decompresses, scans, approves or releases it.
Production execution must additionally sit behind DNS-aware, allowlisted egress
controls to prevent resolution/rebinding from reaching private networks. Network
tooling must not upload repository/customer content or persist credentials.
