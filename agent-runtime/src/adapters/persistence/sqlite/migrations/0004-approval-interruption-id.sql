ALTER TABLE runtime_approval RENAME TO runtime_approval_legacy;

CREATE TABLE runtime_approval (
  id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES runtime_run(id) ON DELETE CASCADE,
  tool_name TEXT NOT NULL,
  interruption_id TEXT NOT NULL,
  reason TEXT NOT NULL,
  requested_by_role TEXT NOT NULL,
  required_authority TEXT NOT NULL,
  payload_digest TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'rejected')),
  decided_by TEXT,
  decision_reason TEXT,
  requested_at TEXT NOT NULL,
  decided_at TEXT,
  UNIQUE(run_id, interruption_id)
);

INSERT INTO runtime_approval (
  id, run_id, tool_name, interruption_id, reason, requested_by_role,
  required_authority, payload_digest, status, decided_by, decision_reason,
  requested_at, decided_at
)
SELECT
  id, run_id, tool_name, 'legacy-' || id, reason, requested_by_role,
  required_authority, payload_digest, status, decided_by, decision_reason,
  requested_at, decided_at
FROM runtime_approval_legacy;

DROP TABLE runtime_approval_legacy;
