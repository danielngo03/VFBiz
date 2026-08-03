import { createHash, randomUUID } from "node:crypto";
import { chmodSync, closeSync, openSync, readFileSync, statSync, unlinkSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { DatabaseSync } from "node:sqlite";
import type { ApprovalDecision, RuntimeApproval } from "../../../domain/approval-decision.js";
import type { ArtifactReference } from "../../../domain/artifact-reference.js";
import { OptimisticConflictError, RuntimeError } from "../../../domain/errors.js";
import type { RuntimeCheckpoint } from "../../../domain/runtime-checkpoint.js";
import type { RuntimeEvent, RuntimeEventType } from "../../../domain/runtime-event.js";
import { canTransition, terminalStates, type EnqueueRunInput, type RuntimeRun, type RuntimeState } from "../../../domain/runtime-run.js";
import type { RunStore, RuntimeUsage, RuntimeUsageTotals } from "../../../ports/run-store.js";
import { StateCipher } from "./state-cipher.js";

type SqlValue = string | number | bigint | null;
type SqlRow = Record<string, SqlValue>;

const migrationDirectory = path.join(
  path.dirname(fileURLToPath(import.meta.url)),
  "migrations",
);

function now(): string {
  return new Date().toISOString();
}

function requiredString(row: SqlRow, key: string): string {
  const value = row[key];
  if (typeof value !== "string") throw new RuntimeError("STORE_CORRUPTION", `missing string column ${key}`);
  return value;
}

function nullableString(row: SqlRow, key: string): string | null {
  const value = row[key];
  if (value === null || value === undefined) return null;
  if (typeof value !== "string") throw new RuntimeError("STORE_CORRUPTION", `invalid string column ${key}`);
  return value;
}

export class SqliteRunStore implements RunStore {
  private readonly database: DatabaseSync;

  public constructor(
    private readonly databasePath: string,
    private readonly cipherFactory: () => StateCipher = () => new StateCipher(),
  ) {
    this.database = new DatabaseSync(databasePath);
  }

  public initialize(): void {
    const releaseMigrationLock = this.acquireMigrationLock();
    try {
      this.database.exec(readFileSync(path.join(migrationDirectory, "0001-initial.sql"), "utf8"));
      this.database.exec("BEGIN IMMEDIATE");
      try {
        const columns = this.database.prepare("PRAGMA table_info(runtime_run)").all() as SqlRow[];
        if (!columns.some((row) => row.name === "governance_claim_id")) {
          this.database.exec(readFileSync(path.join(migrationDirectory, "0002-governance-authority.sql"), "utf8"));
        }
        const eventColumns = this.database.prepare("PRAGMA table_info(runtime_event)").all() as SqlRow[];
        if (!eventColumns.some((row) => row.name === "payload_digest")) {
          this.database.exec(readFileSync(path.join(migrationDirectory, "0003-event-provenance.sql"), "utf8"));
        }
        const approvalColumns = this.database.prepare("PRAGMA table_info(runtime_approval)").all() as SqlRow[];
        if (!approvalColumns.some((row) => row.name === "interruption_id")) {
          this.database.exec(readFileSync(path.join(migrationDirectory, "0004-approval-interruption-id.sql"), "utf8"));
        }
        const usageColumns = this.database.prepare("PRAGMA table_info(runtime_usage)").all() as SqlRow[];
        if (!usageColumns.some((row) => row.name === "idempotency_key")) {
          this.database.exec(readFileSync(path.join(migrationDirectory, "0005-usage-idempotency.sql"), "utf8"));
        }
        const checkpointHasIdempotencyIndex = (this.database.prepare(
          "PRAGMA index_list(runtime_checkpoint)",
        ).all() as SqlRow[]).some((index) => {
          const columnsForIndex = this.database.prepare(
            `PRAGMA index_info(${requiredString(index, "name")})`,
          ).all() as SqlRow[];
          return columnsForIndex.map((column) => column.name).join(",") === "run_id,kind,state_digest";
        });
        if (!checkpointHasIdempotencyIndex) {
          this.database.exec(readFileSync(path.join(migrationDirectory, "0006-checkpoint-idempotency.sql"), "utf8"));
        }
        const legacyEvents = this.database.prepare(`
          SELECT event.id, event.payload_json, run.context_key, run.base_revision
          FROM runtime_event event
          JOIN runtime_run run ON run.id = event.run_id
          WHERE event.payload_digest = ''
        `).all() as SqlRow[];
        const backfill = this.database.prepare(`
          UPDATE runtime_event
          SET context_key = ?, base_revision = ?, payload_digest = ?
          WHERE id = ?
        `);
        for (const event of legacyEvents) {
          const payload = requiredString(event, "payload_json");
          backfill.run(
            nullableString(event, "context_key"),
            nullableString(event, "base_revision"),
            createHash("sha256").update(payload).digest("hex"),
            requiredString(event, "id"),
          );
        }
        this.database.exec("COMMIT");
      } catch (error) {
        this.database.exec("ROLLBACK");
        throw error;
      }
      if (this.databasePath !== ":memory:") chmodSync(this.databasePath, 0o600);
    } finally {
      releaseMigrationLock();
    }
  }

  public assertCheckpointEncryptionReady(): void {
    const cipher = this.cipherFactory();
    const encrypted = cipher.encrypt("vfbiz-runtime-key-preflight");
    if (cipher.decrypt(encrypted.ciphertext) !== "vfbiz-runtime-key-preflight") {
      throw new RuntimeError("STATE_KEY_PREFLIGHT_FAILED", "checkpoint encryption key failed its preflight");
    }
  }

  public enqueue(input: EnqueueRunInput): RuntimeRun {
    const timestamp = now();
    const id = `run-${randomUUID()}`;
    this.database.prepare(`
      INSERT OR IGNORE INTO runtime_run (
        id, work_item_key, idempotency_key, state, mode, objective, workspace,
        owner_team, context_key, base_revision, governance_claim_id,
        governance_fencing_token, budget_json, created_at, updated_at
      ) VALUES (?, ?, ?, 'queued', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `).run(
      id,
      input.workItemKey,
      input.idempotencyKey,
      input.mode,
      input.objective,
      input.workspace,
      input.ownerTeam,
      input.contextKey,
      input.baseRevision,
      input.governanceClaimId,
      input.governanceFencingToken,
      JSON.stringify(input.budget),
      timestamp,
      timestamp,
    );
    const run = this.getRunByIdempotencyKey(input.idempotencyKey);
    if (!run) throw new RuntimeError("STORE_WRITE_FAILED", "runtime enqueue did not return a run");
    this.appendEvent(run.id, "run.enqueued", `enqueue:${input.idempotencyKey}`, {
      workItemKey: input.workItemKey,
      mode: input.mode,
    });
    return run;
  }

  public getRun(runId: string): RuntimeRun | null {
    const row = this.database.prepare("SELECT * FROM runtime_run WHERE id = ?").get(runId) as SqlRow | undefined;
    return row ? this.mapRun(row) : null;
  }

  public listRuns(workItemKey?: string): RuntimeRun[] {
    const rows = workItemKey
      ? this.database.prepare(
          "SELECT * FROM runtime_run WHERE work_item_key = ? ORDER BY updated_at DESC, id",
        ).all(workItemKey) as SqlRow[]
      : this.database.prepare(
          "SELECT * FROM runtime_run ORDER BY updated_at DESC, id",
        ).all() as SqlRow[];
    return rows.map((row) => this.mapRun(row));
  }

  public claimNextRun(workerId: string): RuntimeRun | null {
    return this.transaction(() => {
      const row = this.database.prepare(
        "SELECT * FROM runtime_run WHERE state = 'queued' ORDER BY created_at, id LIMIT 1",
      ).get() as SqlRow | undefined;
      if (!row) return null;
      const run = this.mapRun(row);
      const timestamp = now();
      const result = this.database.prepare(`
        UPDATE runtime_run
        SET state = 'running', claimed_by = ?, heartbeat_at = ?, updated_at = ?, version = version + 1
        WHERE id = ? AND version = ? AND state = 'queued'
      `).run(workerId, timestamp, timestamp, run.id, run.version);
      if (result.changes !== 1) throw new OptimisticConflictError(run.id);
      this.appendEventUnsafe(run.id, "run.claimed", `claim:${run.version + 1}`, { workerId });
      return this.requireRun(run.id);
    });
  }

  public heartbeat(runId: string, workerId: string): RuntimeRun {
    const timestamp = now();
    const result = this.database.prepare(`
      UPDATE runtime_run
      SET heartbeat_at = ?, updated_at = ?
      WHERE id = ? AND claimed_by = ? AND state IN ('running', 'reviewing')
    `).run(timestamp, timestamp, runId, workerId);
    if (result.changes !== 1) {
      throw new RuntimeError("HEARTBEAT_REJECTED", `worker no longer owns active run: ${runId}`);
    }
    return this.requireRun(runId);
  }

  public resumeWaiting(runId: string, expectedVersion: number, workerId: string): RuntimeRun {
    return this.transaction(() => {
      const run = this.requireRun(runId);
      if (run.version !== expectedVersion) throw new OptimisticConflictError(runId);
      if (run.state !== "waiting_approval" && run.state !== "waiting_dependency") {
        throw new RuntimeError("RUN_NOT_RESUMABLE", `runtime run is not waiting: ${run.state}`);
      }
      const timestamp = now();
      const result = this.database.prepare(`
        UPDATE runtime_run
        SET state = 'running', claimed_by = ?, heartbeat_at = ?, updated_at = ?, version = version + 1
        WHERE id = ? AND version = ?
      `).run(workerId, timestamp, timestamp, runId, expectedVersion);
      if (result.changes !== 1) throw new OptimisticConflictError(runId);
      this.appendEventUnsafe(runId, "run.transitioned", `resume:${expectedVersion}:${workerId}`, {
        from: run.state,
        to: "running",
        workerId,
      });
      return this.requireRun(runId);
    });
  }

  public transition(
    runId: string,
    expectedVersion: number,
    to: RuntimeState,
    failureCode?: string,
  ): RuntimeRun {
    return this.transaction(() => {
      const current = this.requireRun(runId);
      if (current.version !== expectedVersion) throw new OptimisticConflictError(runId);
      if (!canTransition(current.state, to)) {
        throw new RuntimeError("INVALID_TRANSITION", `cannot transition ${current.state} to ${to}`);
      }
      const timestamp = now();
      const result = this.database.prepare(`
        UPDATE runtime_run
        SET state = ?, failure_code = ?, updated_at = ?, heartbeat_at = ?, version = version + 1
        WHERE id = ? AND version = ?
      `).run(to, failureCode ?? null, timestamp, timestamp, runId, expectedVersion);
      if (result.changes !== 1) throw new OptimisticConflictError(runId);
      this.appendEventUnsafe(runId, "run.transitioned", `transition:${expectedVersion}:${to}`, {
        from: current.state,
        to,
        failureCode: failureCode ?? null,
      });
      return this.requireRun(runId);
    });
  }

  public requestCancellation(runId: string): RuntimeRun {
    return this.transaction(() => {
      const run = this.requireRun(runId);
      if (terminalStates.has(run.state)) return run;
      const timestamp = now();
      const immediate = run.state !== "running" && run.state !== "reviewing";
      this.database.prepare(`
        UPDATE runtime_run
        SET cancellation_requested_at = ?, state = ?, updated_at = ?, version = version + 1
        WHERE id = ? AND version = ?
      `).run(timestamp, immediate ? "cancelled" : run.state, timestamp, runId, run.version);
      this.appendEventUnsafe(runId, "run.cancel-requested", `cancel:${run.version + 1}`, { immediate });
      return this.requireRun(runId);
    });
  }

  public appendEvent(
    runId: string,
    type: RuntimeEventType,
    idempotencyKey: string,
    payload: Record<string, unknown>,
  ): RuntimeEvent {
    return this.transaction(() => this.appendEventUnsafe(runId, type, idempotencyKey, payload));
  }

  public listEvents(runId: string): RuntimeEvent[] {
    const rows = this.database.prepare(
      "SELECT * FROM runtime_event WHERE run_id = ? ORDER BY sequence",
    ).all(runId) as SqlRow[];
    return rows.map((row) => this.mapEvent(row));
  }

  public saveCheckpoint(
    runId: string,
    kind: RuntimeCheckpoint["kind"],
    plaintextState: string,
  ): RuntimeCheckpoint {
    return this.transaction(() => {
      this.requireRun(runId);
      const encrypted = this.cipherFactory().encrypt(plaintextState);
      const existing = this.database.prepare(`
        SELECT * FROM runtime_checkpoint
        WHERE run_id = ? AND kind = ? AND state_digest = ?
      `).get(runId, kind, encrypted.digest) as SqlRow | undefined;
      if (existing) return this.mapCheckpoint(existing);
      const sequence = this.nextSequence("runtime_checkpoint", runId);
      const checkpoint: RuntimeCheckpoint = {
        id: `checkpoint-${randomUUID()}`,
        runId,
        sequence,
        kind,
        encryptedState: encrypted.ciphertext,
        stateDigest: encrypted.digest,
        createdAt: now(),
      };
      this.database.prepare(`
        INSERT INTO runtime_checkpoint (
          id, run_id, sequence, kind, encrypted_state, state_digest, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
      `).run(
        checkpoint.id,
        checkpoint.runId,
        checkpoint.sequence,
        checkpoint.kind,
        checkpoint.encryptedState,
        checkpoint.stateDigest,
        checkpoint.createdAt,
      );
      this.appendEventUnsafe(runId, "checkpoint.saved", `checkpoint:${sequence}`, {
        checkpointId: checkpoint.id,
        kind,
        stateDigest: checkpoint.stateDigest,
      });
      return checkpoint;
    });
  }

  public getLatestCheckpoint(runId: string): RuntimeCheckpoint | null {
    const row = this.database.prepare(
      "SELECT * FROM runtime_checkpoint WHERE run_id = ? ORDER BY sequence DESC LIMIT 1",
    ).get(runId) as SqlRow | undefined;
    return row ? this.mapCheckpoint(row) : null;
  }

  public decryptCheckpoint(checkpoint: RuntimeCheckpoint): string {
    return this.cipherFactory().decrypt(checkpoint.encryptedState);
  }

  public createApproval(
    input: Omit<RuntimeApproval, "id" | "status" | "decidedBy" | "decisionReason" | "requestedAt" | "decidedAt">,
  ): RuntimeApproval {
    return this.transaction(() => {
      this.requireRun(input.runId);
      const existing = this.database.prepare(`
        SELECT * FROM runtime_approval
        WHERE run_id = ? AND interruption_id = ?
      `).get(input.runId, input.interruptionId) as SqlRow | undefined;
      if (existing) return this.mapApproval(existing);
      const id = `approval-${randomUUID()}`;
      const requestedAt = now();
      this.database.prepare(`
        INSERT INTO runtime_approval (
          id, run_id, tool_name, interruption_id, reason, requested_by_role, required_authority,
          payload_digest, status, requested_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
      `).run(
        id,
        input.runId,
        input.toolName,
        input.interruptionId,
        input.reason,
        input.requestedByRole,
        input.requiredAuthority,
        input.payloadDigest,
        requestedAt,
      );
      this.appendEventUnsafe(input.runId, "approval.requested", `approval-request:${id}`, {
        approvalId: id,
        toolName: input.toolName,
        requiredAuthority: input.requiredAuthority,
      });
      return this.requireApproval(id);
    });
  }

  public getApproval(approvalId: string): RuntimeApproval | null {
    const row = this.database.prepare("SELECT * FROM runtime_approval WHERE id = ?").get(approvalId) as SqlRow | undefined;
    return row ? this.mapApproval(row) : null;
  }

  public listApprovals(status?: RuntimeApproval["status"]): RuntimeApproval[] {
    const rows = status
      ? (this.database.prepare(
          "SELECT * FROM runtime_approval WHERE status = ? ORDER BY requested_at",
        ).all(status) as SqlRow[])
      : (this.database.prepare(
          "SELECT * FROM runtime_approval ORDER BY requested_at",
        ).all() as SqlRow[]);
    return rows.map((row) => this.mapApproval(row));
  }

  public decideApproval(decision: ApprovalDecision): RuntimeApproval {
    return this.transaction(() => {
      const approval = this.requireApproval(decision.approvalId);
      if (decision.decidedBy !== `human:${approval.requiredAuthority}`) {
        throw new RuntimeError(
          "APPROVAL_AUTHORITY_MISMATCH",
          `approval requires human:${approval.requiredAuthority}`,
        );
      }
      if (approval.status !== "pending") return approval;
      const decidedAt = now();
      const result = this.database.prepare(`
        UPDATE runtime_approval
        SET status = ?, decided_by = ?, decision_reason = ?, decided_at = ?
        WHERE id = ? AND status = 'pending'
      `).run(decision.decision, decision.decidedBy, decision.reason, decidedAt, decision.approvalId);
      if (result.changes !== 1) throw new RuntimeError("APPROVAL_CONFLICT", "approval changed concurrently", true);
      this.appendEventUnsafe(approval.runId, "approval.decided", `approval-decision:${approval.id}`, {
        approvalId: approval.id,
        decision: decision.decision,
        decidedBy: decision.decidedBy,
      });
      return this.requireApproval(approval.id);
    });
  }

  public recordArtifact(input: Omit<ArtifactReference, "id" | "createdAt">): ArtifactReference {
    return this.transaction(() => {
      this.requireRun(input.runId);
      const existing = this.database.prepare(`
        SELECT * FROM runtime_artifact WHERE run_id = ? AND path = ? AND sha256 = ?
      `).get(input.runId, input.path, input.sha256) as SqlRow | undefined;
      if (existing) return this.mapArtifact(existing);
      const artifact: ArtifactReference = {
        ...input,
        id: `artifact-${randomUUID()}`,
        createdAt: now(),
      };
      this.database.prepare(`
        INSERT INTO runtime_artifact (id, run_id, kind, path, sha256, media_type, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
      `).run(
        artifact.id,
        artifact.runId,
        artifact.kind,
        artifact.path,
        artifact.sha256,
        artifact.mediaType,
        artifact.createdAt,
      );
      this.appendEventUnsafe(input.runId, "artifact.recorded", `artifact:${artifact.id}`, {
        artifactId: artifact.id,
        sha256: artifact.sha256,
      });
      return artifact;
    });
  }

  public listArtifacts(runId: string): ArtifactReference[] {
    this.requireRun(runId);
    const rows = this.database.prepare(
      "SELECT * FROM runtime_artifact WHERE run_id = ? ORDER BY created_at, id",
    ).all(runId) as SqlRow[];
    return rows.map((row) => this.mapArtifact(row));
  }

  public recordUsage(runId: string, usage: RuntimeUsage, idempotencyKey: string): void {
    this.transaction(() => {
      this.requireRun(runId);
      const existing = this.database.prepare(`
        SELECT id FROM runtime_usage WHERE run_id = ? AND idempotency_key = ?
      `).get(runId, idempotencyKey) as SqlRow | undefined;
      if (existing) return;
      this.database.prepare(`
        INSERT INTO runtime_usage (
          run_id, idempotency_key, input_tokens, output_tokens, estimated_usd, model, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
      `).run(
        runId,
        idempotencyKey,
        usage.inputTokens,
        usage.outputTokens,
        usage.estimatedUsd,
        usage.model,
        now(),
      );
      this.appendEventUnsafe(runId, "usage.recorded", `usage:${idempotencyKey}`, {
        inputTokens: usage.inputTokens,
        outputTokens: usage.outputTokens,
        model: usage.model,
      });
    });
  }

  public getUsageTotals(runId: string): RuntimeUsageTotals {
    this.requireRun(runId);
    const usage = this.database.prepare(`
      SELECT
        COALESCE(SUM(input_tokens), 0) AS input_tokens,
        COALESCE(SUM(output_tokens), 0) AS output_tokens,
        CASE WHEN COUNT(*) = SUM(CASE WHEN estimated_usd IS NOT NULL THEN 1 ELSE 0 END)
          THEN COALESCE(SUM(estimated_usd), 0)
          ELSE NULL
        END AS estimated_usd
      FROM runtime_usage WHERE run_id = ?
    `).get(runId) as SqlRow;
    const attempts = this.database.prepare(`
      SELECT COUNT(*) AS count FROM runtime_event
      WHERE run_id = ? AND type = 'run.claimed'
    `).get(runId) as SqlRow;
    return {
      inputTokens: Number(usage.input_tokens),
      outputTokens: Number(usage.output_tokens),
      estimatedUsd: usage.estimated_usd === null ? null : Number(usage.estimated_usd),
      model: null,
      attempts: Number(attempts.count),
    };
  }

  public reconcileStale(staleBefore: string): RuntimeRun[] {
    return this.transaction(() => {
      const rows = this.database.prepare(`
        SELECT * FROM runtime_run
        WHERE state IN ('running', 'reviewing')
          AND heartbeat_at IS NOT NULL
          AND heartbeat_at < ?
      `).all(staleBefore) as SqlRow[];
      const reconciled: RuntimeRun[] = [];
      for (const row of rows) {
        const run = this.mapRun(row);
        const nextState = run.cancellationRequestedAt ? "cancelled" : "queued";
        this.database.prepare(`
          UPDATE runtime_run
          SET state = ?, claimed_by = NULL, heartbeat_at = NULL,
              updated_at = ?, version = version + 1
          WHERE id = ? AND version = ?
        `).run(nextState, now(), run.id, run.version);
        this.appendEventUnsafe(run.id, "run.reconciled", `reconcile:${run.version + 1}`, {
          previousWorker: run.claimedBy,
          to: nextState,
        });
        reconciled.push(this.requireRun(run.id));
      }
      return reconciled;
    });
  }

  public close(): void {
    this.database.close();
  }

  private appendEventUnsafe(
    runId: string,
    type: RuntimeEventType,
    idempotencyKey: string,
    payload: Record<string, unknown>,
  ): RuntimeEvent {
    const run = this.requireRun(runId);
    const existing = this.database.prepare(`
      SELECT * FROM runtime_event WHERE run_id = ? AND idempotency_key = ?
    `).get(runId, idempotencyKey) as SqlRow | undefined;
    if (existing) return this.mapEvent(existing);
    const payloadJson = JSON.stringify(payload);
    const actor = typeof payload.decidedBy === "string"
      ? payload.decidedBy
      : typeof payload.workerId === "string"
        ? `worker:${payload.workerId}`
        : "runtime";
    const event: RuntimeEvent = {
      id: `event-${randomUUID()}`,
      runId,
      sequence: this.nextSequence("runtime_event", runId),
      type,
      idempotencyKey,
      actor,
      contextKey: run.contextKey,
      baseRevision: run.baseRevision,
      payloadDigest: createHash("sha256").update(payloadJson).digest("hex"),
      payload,
      createdAt: now(),
    };
    this.database.prepare(`
      INSERT INTO runtime_event (
        id, run_id, sequence, type, idempotency_key, actor, context_key,
        base_revision, payload_digest, payload_json, created_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `).run(
      event.id,
      event.runId,
      event.sequence,
      event.type,
      event.idempotencyKey,
      event.actor,
      event.contextKey,
      event.baseRevision,
      event.payloadDigest,
      payloadJson,
      event.createdAt,
    );
    return event;
  }

  private nextSequence(table: "runtime_event" | "runtime_checkpoint" | "runtime_usage", runId: string): number {
    const column = table === "runtime_usage" ? "id" : "sequence";
    const row = this.database.prepare(
      `SELECT COALESCE(MAX(${column}), 0) + 1 AS next FROM ${table} WHERE run_id = ?`,
    ).get(runId) as SqlRow;
    return Number(row.next);
  }

  private getRunByIdempotencyKey(key: string): RuntimeRun | null {
    const row = this.database.prepare("SELECT * FROM runtime_run WHERE idempotency_key = ?").get(key) as SqlRow | undefined;
    return row ? this.mapRun(row) : null;
  }

  private requireRun(runId: string): RuntimeRun {
    const run = this.getRun(runId);
    if (!run) throw new RuntimeError("RUN_NOT_FOUND", `runtime run not found: ${runId}`);
    return run;
  }

  private requireApproval(approvalId: string): RuntimeApproval {
    const approval = this.getApproval(approvalId);
    if (!approval) throw new RuntimeError("APPROVAL_NOT_FOUND", `runtime approval not found: ${approvalId}`);
    return approval;
  }

  private transaction<T>(operation: () => T): T {
    this.database.exec("BEGIN IMMEDIATE");
    try {
      const result = operation();
      this.database.exec("COMMIT");
      return result;
    } catch (error) {
      this.database.exec("ROLLBACK");
      throw error;
    }
  }

  private acquireMigrationLock(): () => void {
    if (this.databasePath === ":memory:") return () => undefined;
    const lockPath = `${this.databasePath}.migrate.lock`;
    const deadline = Date.now() + 10_000;
    while (true) {
      try {
        const descriptor = openSync(lockPath, "wx", 0o600);
        return () => {
          closeSync(descriptor);
          unlinkSync(lockPath);
        };
      } catch (error) {
        const code = error instanceof Error && "code" in error ? String(error.code) : "";
        if (code !== "EEXIST") throw error;
        const lockAge = (() => {
          try {
            return Date.now() - statSync(lockPath).mtimeMs;
          } catch (statError) {
            const statCode = statError instanceof Error && "code" in statError ? String(statError.code) : "";
            if (statCode === "ENOENT") return null;
            throw statError;
          }
        })();
        if (lockAge === null) continue;
        const stale = lockAge > 120_000;
        if (stale) {
          unlinkSync(lockPath);
          continue;
        }
        if (Date.now() >= deadline) {
          throw new RuntimeError("MIGRATION_LOCK_TIMEOUT", "timed out waiting for runtime schema initialization");
        }
        Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 25);
      }
    }
  }

  private mapRun(row: SqlRow): RuntimeRun {
    return {
      id: requiredString(row, "id"),
      workItemKey: requiredString(row, "work_item_key"),
      idempotencyKey: requiredString(row, "idempotency_key"),
      state: requiredString(row, "state") as RuntimeState,
      mode: requiredString(row, "mode") as RuntimeRun["mode"],
      objective: requiredString(row, "objective"),
      workspace: requiredString(row, "workspace"),
      ownerTeam: nullableString(row, "owner_team"),
      contextKey: nullableString(row, "context_key"),
      baseRevision: nullableString(row, "base_revision"),
      governanceClaimId: nullableString(row, "governance_claim_id"),
      governanceFencingToken:
        row.governance_fencing_token === null || row.governance_fencing_token === undefined
          ? null
          : Number(row.governance_fencing_token),
      claimedBy: nullableString(row, "claimed_by"),
      heartbeatAt: nullableString(row, "heartbeat_at"),
      cancellationRequestedAt: nullableString(row, "cancellation_requested_at"),
      failureCode: nullableString(row, "failure_code"),
      version: Number(row.version),
      budget: JSON.parse(requiredString(row, "budget_json")) as RuntimeRun["budget"],
      createdAt: requiredString(row, "created_at"),
      updatedAt: requiredString(row, "updated_at"),
    };
  }

  private mapEvent(row: SqlRow): RuntimeEvent {
    return {
      id: requiredString(row, "id"),
      runId: requiredString(row, "run_id"),
      sequence: Number(row.sequence),
      type: requiredString(row, "type") as RuntimeEventType,
      idempotencyKey: requiredString(row, "idempotency_key"),
      actor: requiredString(row, "actor"),
      contextKey: nullableString(row, "context_key"),
      baseRevision: nullableString(row, "base_revision"),
      payloadDigest: requiredString(row, "payload_digest"),
      payload: JSON.parse(requiredString(row, "payload_json")) as Record<string, unknown>,
      createdAt: requiredString(row, "created_at"),
    };
  }

  private mapCheckpoint(row: SqlRow): RuntimeCheckpoint {
    return {
      id: requiredString(row, "id"),
      runId: requiredString(row, "run_id"),
      sequence: Number(row.sequence),
      kind: requiredString(row, "kind") as RuntimeCheckpoint["kind"],
      encryptedState: requiredString(row, "encrypted_state"),
      stateDigest: requiredString(row, "state_digest"),
      createdAt: requiredString(row, "created_at"),
    };
  }

  private mapApproval(row: SqlRow): RuntimeApproval {
    return {
      id: requiredString(row, "id"),
      runId: requiredString(row, "run_id"),
      toolName: requiredString(row, "tool_name"),
      interruptionId: requiredString(row, "interruption_id"),
      reason: requiredString(row, "reason"),
      requestedByRole: requiredString(row, "requested_by_role"),
      requiredAuthority: requiredString(row, "required_authority"),
      payloadDigest: requiredString(row, "payload_digest"),
      status: requiredString(row, "status") as RuntimeApproval["status"],
      decidedBy: nullableString(row, "decided_by"),
      decisionReason: nullableString(row, "decision_reason"),
      requestedAt: requiredString(row, "requested_at"),
      decidedAt: nullableString(row, "decided_at"),
    };
  }

  private mapArtifact(row: SqlRow): ArtifactReference {
    return {
      id: requiredString(row, "id"),
      runId: requiredString(row, "run_id"),
      kind: requiredString(row, "kind") as ArtifactReference["kind"],
      path: requiredString(row, "path"),
      sha256: requiredString(row, "sha256"),
      mediaType: requiredString(row, "media_type"),
      createdAt: requiredString(row, "created_at"),
    };
  }
}
