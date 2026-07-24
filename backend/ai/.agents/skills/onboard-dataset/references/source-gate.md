# Source and download gate

Before network access, the Source Register entry must validate against
`contracts/ai/source-register.schema.json` and contain:

- `status: approved`;
- Data Owner, custodian và requested purpose nằm trong `approved_purposes`
  (đồng thời là subset của `proposed_purposes`);
- pinned source revision and SHA-256 checksum;
- Legal evidence with commercial use, derivative use and access conditions accepted;
- classification, non-empty `acl_namespaces`, retention and deletion method;
- approval evidence that identifies the human decision.

Gated access, click-through terms, conflicting license metadata, missing upstream
rights or non-commercial/no-derivatives terms are not “probably safe”. Keep the
entry at `legal-hold`/`rejected` and return `failed-safely`.

Download uses an allowlisted host and quarantine destination. Redirect target,
content length/type and final checksum are verified. Network tooling must not
upload repository/customer content or persist credentials.
