ALTER TABLE "conversation_turn"
ADD COLUMN "assistantReleaseRevision" VARCHAR(160);

ALTER TABLE "conversation_turn"
ADD CONSTRAINT "conversation_turn_release_revision_nonempty"
CHECK (
  "assistantReleaseRevision" IS NULL
  OR length(btrim("assistantReleaseRevision")) > 0
);
