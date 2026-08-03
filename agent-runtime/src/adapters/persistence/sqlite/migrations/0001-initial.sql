PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;

CREATE TABLE IF NOT EXISTS runtime_run (
  id TEXT PRIMARY KEY,
  work_item_key TEXT NOT NULL,
  idempotency_key TEXT NOT NULL UNIQUE,
  state TEXT NOT NULL CHECK (state IN (
    'queued', 'running', 'waiting_approval', 'waiting_dependency', 'reviewing',
    'succeeded', 'failed_safely', 'cancelled'
  )),
  mode TEXT NOT NULL CHECK (mode IN ('discovery', 'bounded', 'controlled')),
  objective TEXT NOT NULL,
  workspace TEXT NOT NULL,
  owner_team TEXT,
  context_key TEXT,
  base_revision TEXT,
  governance_claim_id TEXT,
  governance_fencing_token INTEGER,
  claimed_by TEXT,
  heartbeat_at TEXT,
  cancellation_requested_at TEXT,
  failure_code TEXT,
  version INTEGER NOT NULL DEFAULT 1,
  budget_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS runtime_run_queue_idx
  ON runtime_run(state, created_at);

CREATE TABLE IF NOT EXISTS runtime_event (
  id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES runtime_run(id) ON DELETE CASCADE,
  sequence INTEGER NOT NULL,
  type TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  actor TEXT NOT NULL,
  context_key TEXT,
  base_revision TEXT,
  payload_digest TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(run_id, sequence),
  UNIQUE(run_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS runtime_checkpoint (
  id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES runtime_run(id) ON DELETE CASCADE,
  sequence INTEGER NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('workflow', 'agent-state')),
  encrypted_state TEXT NOT NULL,
  state_digest TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(run_id, sequence),
  UNIQUE(run_id, kind, state_digest)
);

CREATE TABLE IF NOT EXISTS runtime_approval (
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

CREATE TABLE IF NOT EXISTS runtime_artifact (
  id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES runtime_run(id) ON DELETE CASCADE,
  kind TEXT NOT NULL,
  path TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  media_type TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(run_id, path, sha256)
);

CREATE TABLE IF NOT EXISTS runtime_usage (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL REFERENCES runtime_run(id) ON DELETE CASCADE,
  idempotency_key TEXT NOT NULL,
  input_tokens INTEGER NOT NULL CHECK (input_tokens >= 0),
  output_tokens INTEGER NOT NULL CHECK (output_tokens >= 0),
  estimated_usd REAL,
  model TEXT,
  created_at TEXT NOT NULL,
  UNIQUE(run_id, idempotency_key)
);
