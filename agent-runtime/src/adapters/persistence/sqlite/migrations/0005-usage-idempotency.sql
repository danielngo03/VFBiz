ALTER TABLE runtime_usage RENAME TO runtime_usage_legacy;

CREATE TABLE runtime_usage (
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

INSERT INTO runtime_usage (
  id, run_id, idempotency_key, input_tokens, output_tokens,
  estimated_usd, model, created_at
)
SELECT
  id, run_id, 'legacy-' || id, input_tokens, output_tokens,
  estimated_usd, model, created_at
FROM runtime_usage_legacy;

DROP TABLE runtime_usage_legacy;
