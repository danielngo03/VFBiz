-- Session-level public events (e.g. session.closed) have no owning turn,
-- unlike every event type that existed when this column was first created.
ALTER TABLE "conversation_public_event"
  ALTER COLUMN "conversationTurnId" DROP NOT NULL;

ALTER TABLE "conversation_runtime"
  DROP CONSTRAINT "conversation_runtime_status_check";

ALTER TABLE "conversation_runtime"
  ADD CONSTRAINT "conversation_runtime_status_check"
    CHECK ("runtimeStatus" IN ('open', 'handoff', 'closed'));
