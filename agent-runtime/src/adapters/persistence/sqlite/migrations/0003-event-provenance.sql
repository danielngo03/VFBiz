ALTER TABLE runtime_event ADD COLUMN actor TEXT NOT NULL DEFAULT 'runtime';
ALTER TABLE runtime_event ADD COLUMN context_key TEXT;
ALTER TABLE runtime_event ADD COLUMN base_revision TEXT;
ALTER TABLE runtime_event ADD COLUMN payload_digest TEXT NOT NULL DEFAULT '';
