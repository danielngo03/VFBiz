ALTER TABLE "session_projection"
  ADD COLUMN "emailVerified" BOOLEAN,
  ADD COLUMN "mfaSatisfied" BOOLEAN NOT NULL DEFAULT false;
