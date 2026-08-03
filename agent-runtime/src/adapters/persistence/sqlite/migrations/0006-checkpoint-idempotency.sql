CREATE UNIQUE INDEX runtime_checkpoint_run_kind_digest_uq
  ON runtime_checkpoint(run_id, kind, state_digest);
