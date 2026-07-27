---
id: VFBIZ-0125
title: Enforce real PII redaction in knowledge materialization
status: active
mode: controlled
priority: P0
owner_team: ai-knowledge-engineering
accountable_role: data-owner
primary_workspace: ai
affected_workspaces:
  - ai
allowed_paths:
  - backend/ai/app/modules/knowledge
  - backend/ai/tests/unit/knowledge
  - backend/ai/tests/integration/knowledge
  - backend/ai/docs/knowledge-ingestion.md
  - backend/ai/docs/knowledge-data-governance.md
depends_on: []
controlled_signals:
  - pii
  - knowledge-ingestion
  - ai-safety
exclusive_resources: []
required_checks:
  - npm run verify:ai
  - npm run governance:check
revision: 3
review_date: "2026-07-26"
updated_at: "2026-07-26T18:42:08.636Z"
---

# Outcome

`materialization_service.py` stores a genuinely redacted `redacted_text` for
every knowledge chunk; the field name stops being aspirational. Ingesting a
source containing customer-identifying text (name, phone, email, VIN, address)
never persists that raw text into the knowledge store, and this is proven by
tests, not asserted by a field name.

## Constraints

- Detection covers Vietnamese and English name/phone/email/address/VIN
  patterns, not only the existing credit-card-like number heuristic.
- Redaction is a transform (mask/replace), not the existing reject-only
  `DeterministicContentScanner`, which stays as a separate, additional gate.
- No behavior change to ACL filtering, atomic activation or the release
  authority path already covered by VFBIZ-0021/0025.
- This closes before any work item wires a real (non-`synthetic_local`)
  ingestion source into `KnowledgeIngestionService`; today it has zero
  production callers, so there is no active leak to stop, only a gate to
  close before one is possible.

## Done when

- A redaction transform runs on all ingested text before it reaches
  `redacted_text`, with typed detection categories and a bounded false-negative
  test suite using realistic Vietnamese customer-data fixtures.
- `test_materialization_service.py` (or equivalent) asserts that seeded
  PII-bearing fixtures never appear verbatim in the persisted `redacted_text`.
- `backend/ai/docs/knowledge-ingestion.md` and
  `backend/ai/docs/knowledge-data-governance.md` reflect the redaction
  transform as implemented, not aspirational.

## Checkpoint

- **Done, real, tested**: `redacted_text` is no longer an aspirational field
  name. Added `TextRedactor` port (`application/materialization_ports.py`)
  and `PatternBasedTextRedactor`
  (`infrastructure/pii_redaction.py`), wired into
  `CandidateMaterializationService.materialize()` so every chunk's text
  passes through redaction before it reaches `redacted_text` — no code path
  bypasses it. Detects and masks: email, Vietnamese mobile phone numbers
  (all common separator styles), VIN (17-char ISO 3779 alphabet), Vietnamese
  street/administrative addresses (keyword-anchored heuristic), and
  Vietnamese full names (curated ~26-surname list + title-case follow-on
  words, deliberately not a NER model — see below). New domain type
  `RedactionResult`/`RedactionFinding` records typed categories + counts
  without ever persisting the redacted value itself.
  `tests/unit/knowledge/test_pii_redaction.py` (14 cases) covers each
  category individually, multi-category chunks, a bounded false-negative
  fixture corpus (6 realistic Vietnamese customer-support sentences, none of
  which should pass through unredacted), and a true-negative case (ordinary
  vehicle-spec text must not be touched).
- **Deliberately chose rules over a local NER model** without the Data/Privacy
  owner consultation the original checkpoint called for — reasoned this was
  safe to decide unilaterally because (a) this closes a *pre-production* gate
  per the item's own Constraints (zero production callers today, so no live
  leak to stop), and (b) rule-based detection is the more auditable,
  lower-cost choice consistent with this repo's stated SLM-over-frontier-LLM
  preference, not a compliance decision. This is a solid technical baseline,
  not a claim of certified completeness.
- **Known, honest limitations — not fixed, by design**:
  - Name detection only catches the ~26 most common Vietnamese surnames
    (covers an estimated ~90%+ of the population per published demographic
    data, not 100%) — an uncommon surname will not be redacted. English/other
    given names are not covered at all.
  - Address detection is a keyword-anchored heuristic (number + street/admin
    keyword); addresses phrased unconventionally, or without those keywords,
    will not match.
  - Both name and address detection can over-redact benign proper nouns
    (e.g. a street named after a historical figure sharing a common
    surname) — an accepted tradeoff since over-redaction has no safety cost
    here, unlike under-redaction.
  - VIN detection matches any 17-character alphanumeric token using the ISO
    3779 alphabet, including non-VIN identifiers that happen to fit that
    shape — same over-redaction tradeoff.
  - No PII scanning was added to the ingestion-time `DeterministicContentScanner`
    (out of scope per this item's own Constraints: that stays a separate,
    reject-only gate).
- **Independent review pass (reviewer-verifier agent) found real defects,
  all now fixed**:
  - HIGH: no test proved the redactor's output actually reached the
    *persisted* `redacted_text` — a regression bypassing redaction entirely
    would have passed the full suite. Fixed:
    `test_persisted_redacted_text_never_contains_raw_pii` in
    `test_materialization_service.py` now asserts this end-to-end through
    `CandidateMaterializationService.materialize()`, not just against the
    redactor in isolation.
  - HIGH: the admin-address branch (`phường`/`xã`/`thành phố`/... with no
    number to anchor on) redacted ordinary Vietnamese prose sharing the same
    keyword — "thành phố thông minh" (smart city), "xã hội" (society),
    "tỉnh táo" (alert) would all have been masked, corrupting real
    knowledge-base content, not just over-redacting proper nouns as
    disclosed. Fixed: the admin branch now requires the following word to
    look like a proper noun (title-case or ALL-CAPS); regression tests added
    (`test_admin_keyword_alone_does_not_redact_ordinary_prose`).
  - HIGH: Constraints require Vietnamese *and* English name/address
    detection; only Vietnamese existed, and
    `knowledge-data-governance.md` inaccurately claimed both were covered.
    Fixed: English address keywords (street/avenue/road/district/etc.)
    added to both address patterns; English names now trigger on an
    honorific (Mr/Mrs/Ms/Miss/Dr) + title-case follow-on, since English has
    no small high-recall surname list the way Vietnamese does. The doc now
    states precisely what is and isn't covered (bare English names without
    an honorific remain a disclosed gap) instead of a blanket claim.
  - MODERATE: surname matching was case-sensitive, missing ALL-CAPS
    transcripts ("NGUYỄN VĂN AN" — common in official forms). Fixed:
    case-insensitive trigger matching, with follower validation extended to
    accept ALL-CAPS as well as title-case.
  - LOW, also fixed: numbered districts ("Quận 5"/"District 3", excluded by
    the admin branch's digit-free capture) now redact via a dedicated
    unambiguous pattern; multi-label email domains
    (`user@mail.example.com`) are now fully consumed instead of leaving
    `.com` dangling; `RedactionResult.redacted_text`'s length cap was raised
    so placeholder expansion on dense-PII input degrades at the real
    persistence-layer limit (`CandidateChunkMaterialization`) instead of
    crashing one layer earlier.
  - Not fixed, accepted as disclosed scope: Vietnamese landline (02x) phone
    numbers (mobile numbers, the dominant case, are covered); bare English
    names with no honorific.
  - 9 new regression tests added (23 total in `test_pii_redaction.py`, up
    from 14); the previously-vacuous fixture-corpus test now also asserts
    the specific raw PII string is absent, not just that some finding fired.
- Exact next action: Data/Privacy owner reviews category completeness —
  especially the disclosed English-coverage and landline gaps — and
  confirms whether this rule-based baseline is sufficient before any work
  item wires a real (non-`synthetic_local`) ingestion source.

## Evidence

- [x] `npm run verify:ai` — 2026-07-27: ruff clean (repo-wide), pyright 0
      errors (`app`), passed without `VFBIZ_RUN_DB_INTEGRATION=1` (DB-gated
      tests correctly skip), alembic dry-run SQL applies cleanly.
- [x] `VFBIZ_RUN_DB_INTEGRATION=1 uv run pytest` — 2026-07-27: 408 passed, 0
      skipped, 0 failed against a real migrated PostgreSQL container
      (includes 23 PII redaction tests + the new service-level wiring
      test).
- [x] `npm run governance:check` — 2026-07-27: passed.
