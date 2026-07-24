import { createHash, randomUUID } from "node:crypto";
import { readFile } from "node:fs/promises";
import Redis from "ioredis";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

function loadEnvironment(source: string): void {
  for (const line of source.split(/\r?\n/u)) {
    if (line.trim() === "" || line.trimStart().startsWith("#")) continue;
    const index = line.indexOf("=");
    if (index < 1) continue;
    process.env[line.slice(0, index)] = line.slice(index + 1);
  }
}

function redisKey(prefix: string, value: string): string {
  const digest = createHash("sha256").update(value).digest("hex");
  return `vfbiz:customer:${prefix}:${digest}`;
}

describe("Redis customer token vault (integration)", () => {
  let redis: Redis;
  let vault: typeof import("@/platform/session/redis-token-vault");
  let reconciler: typeof import("@/platform/session/provider-revocation-reconciler");
  const subjects: string[] = [];
  const revocationTaskIds: string[] = [];

  beforeAll(async () => {
    loadEnvironment(await readFile(".env.local", "utf8"));
    vault = await import("@/platform/session/redis-token-vault");
    reconciler =
      await import("@/platform/session/provider-revocation-reconciler");
    redis = new Redis(process.env.CUSTOMER_REDIS_URL as string);
  });

  afterAll(async () => {
    await Promise.all(
      subjects.map((subject) => vault.deleteAllSessions(subject)),
    );
    await Promise.all(
      revocationTaskIds.map((id) => vault.deleteProviderRevocationTask(id)),
    );
    await redis.quit();
  });

  it("encrypts token material and deletes every session for a subject", async () => {
    const subject = `integration-customer-${randomUUID()}`;
    subjects.push(subject);
    const now = new Date();
    const ids = [vault.newSessionId(), vault.newSessionId()];
    for (const id of ids) {
      await vault.writeSession(
        {
          authenticatedAt: now,
          csrfToken: randomUUID(),
          deviceLabel: "Integration browser",
          emailVerified: true,
          expiresAt: new Date(now.getTime() + 60 * 60 * 1_000),
          id,
          lastSeenAt: now,
          mfaSatisfied: false,
          networkHint: "127.0.0.0/24",
          providerSessionId: `provider-${id}`,
          subject,
          userAgentSummary: "Integration test agent",
        },
        {
          accessToken: `access-secret-${id}`,
          expiresAt: new Date(now.getTime() + 5 * 60 * 1_000),
          refreshToken: `refresh-secret-${id}`,
        },
      );
    }

    const raw = await redis.get(redisKey("session", ids[0]));
    expect(raw).not.toBeNull();
    expect(raw).not.toContain("access-secret");
    expect(raw).not.toContain("refresh-secret");
    expect(await vault.listSessions(subject)).toHaveLength(2);
    expect(await vault.deleteAllSessions(subject)).toBe(2);
    expect(await vault.listSessions(subject)).toHaveLength(0);
  });

  it("deletes only sessions linked to a Keycloak provider session", async () => {
    const subject = `integration-provider-${randomUUID()}`;
    subjects.push(subject);
    const providerSessionId = `provider-${randomUUID()}`;
    const now = new Date();
    const id = vault.newSessionId();
    await vault.writeSession(
      {
        authenticatedAt: now,
        csrfToken: randomUUID(),
        deviceLabel: null,
        emailVerified: true,
        expiresAt: new Date(now.getTime() + 60 * 60 * 1_000),
        id,
        lastSeenAt: now,
        mfaSatisfied: true,
        networkHint: null,
        providerSessionId,
        subject,
        userAgentSummary: null,
      },
      {
        accessToken: "provider-access-secret",
        expiresAt: new Date(now.getTime() + 5 * 60 * 1_000),
        refreshToken: "provider-refresh-secret",
      },
    );

    expect(await vault.deleteProviderSessions(providerSessionId)).toBe(1);
    expect(await vault.readSession(id)).toBeNull();
  });

  it("commits a replay marker only after logout work succeeds", async () => {
    const jti = randomUUID();
    const first = await vault.beginBackchannelLogoutToken(jti);
    expect(first.state).toBe("acquired");
    if (first.state !== "acquired") throw new Error("Missing logout claim.");

    expect(await vault.beginBackchannelLogoutToken(jti)).toEqual({
      state: "in_progress",
    });
    await vault.releaseBackchannelLogoutToken(jti, first.token);

    const retry = await vault.beginBackchannelLogoutToken(jti);
    expect(retry.state).toBe("acquired");
    if (retry.state !== "acquired") throw new Error("Missing retry claim.");
    expect(
      await vault.completeBackchannelLogoutToken(jti, retry.token),
    ).toBe(true);
    expect(await vault.beginBackchannelLogoutToken(jti)).toEqual({
      state: "completed",
    });
  });

  it("does not let an in-flight refresh resurrect logout-all sessions", async () => {
    const subject = `integration-refresh-fence-${randomUUID()}`;
    subjects.push(subject);
    const now = new Date(Date.now() - 1_000);
    const id = vault.newSessionId();
    const session = {
      authenticatedAt: now,
      csrfToken: randomUUID(),
      deviceLabel: null,
      emailVerified: true as const,
      expiresAt: new Date(now.getTime() + 60 * 60 * 1_000),
      id,
      lastSeenAt: now,
      mfaSatisfied: true,
      networkHint: null,
      providerSessionId: `provider-${randomUUID()}`,
      subject,
      userAgentSummary: null,
    };
    await vault.writeSession(session, {
      accessToken: "old-access-token",
      expiresAt: new Date(now.getTime() + 60_000),
      refreshToken: "old-refresh-token",
    });
    const staleRead = await vault.readSession(id, { touch: false });
    expect(staleRead).not.toBeNull();
    if (staleRead === null) throw new Error("Missing initial session.");

    expect(await vault.deleteAllSessions(subject)).toBe(1);
    expect(
      await vault.writeSession(
        session,
        {
          accessToken: "rotated-access-token",
          expiresAt: new Date(now.getTime() + 120_000),
          refreshToken: "rotated-refresh-token",
        },
        { expectedRevision: staleRead.revision },
      ),
    ).toBeNull();
    expect(await vault.readSession(id)).toBeNull();
  });

  it("fences login callbacks concurrent with subject or provider logout", async () => {
    const subject = `integration-login-fence-${randomUUID()}`;
    subjects.push(subject);
    const providerSessionId = `provider-${randomUUID()}`;
    const authenticatedAt = new Date(Date.now() - 1_000);
    await vault.deleteAllSessions(subject);
    const subjectFencedId = vault.newSessionId();
    const common = {
      authenticatedAt,
      csrfToken: randomUUID(),
      deviceLabel: null,
      emailVerified: true as const,
      expiresAt: new Date(Date.now() + 60 * 60 * 1_000),
      lastSeenAt: new Date(),
      mfaSatisfied: true,
      networkHint: null,
      subject,
      userAgentSummary: null,
    };
    expect(
      await vault.writeSession(
        {
          ...common,
          id: subjectFencedId,
          providerSessionId,
        },
        {
          accessToken: "subject-fenced-access",
          expiresAt: new Date(Date.now() + 60_000),
        },
      ),
    ).toBeNull();

    const secondProviderSessionId = `provider-${randomUUID()}`;
    await vault.deleteProviderSessions(secondProviderSessionId);
    expect(
      await vault.writeSession(
        {
          ...common,
          authenticatedAt: new Date(Date.now() + 1_000),
          id: vault.newSessionId(),
          providerSessionId: secondProviderSessionId,
        },
        {
          accessToken: "provider-fenced-access",
          expiresAt: new Date(Date.now() + 60_000),
        },
      ),
    ).toBeNull();
  });

  it("fails closed and removes a corrupted encrypted session", async () => {
    const subject = `integration-corrupt-${randomUUID()}`;
    subjects.push(subject);
    const id = vault.newSessionId();
    const now = new Date();
    await vault.writeSession(
      {
        authenticatedAt: now,
        csrfToken: randomUUID(),
        deviceLabel: null,
        emailVerified: true,
        expiresAt: new Date(now.getTime() + 60 * 60 * 1_000),
        id,
        lastSeenAt: now,
        mfaSatisfied: false,
        networkHint: null,
        providerSessionId: `provider-${randomUUID()}`,
        subject,
        userAgentSummary: null,
      },
      {
        accessToken: "corrupt-access-secret",
        expiresAt: new Date(now.getTime() + 5 * 60 * 1_000),
        refreshToken: "corrupt-refresh-secret",
      },
    );
    const sessionKey = redisKey("session", id);
    await redis.set(sessionKey, "not-an-authenticated-ciphertext");

    expect(await vault.readSession(id)).toBeNull();
    expect(await redis.exists(sessionKey)).toBe(0);
  });

  it("encrypts failed provider revocation tokens and retries them", async () => {
    const now = new Date("2026-07-24T08:00:00.000Z");
    const refreshToken = `provider-retry-secret-${randomUUID()}`;
    const providerSessionId = `provider-session-${randomUUID()}`;
    expect(
      await reconciler.revokeOrEnqueueProviderToken(
        { now, providerSessionId, refreshToken },
        async () => false,
      ),
    ).toBe("pending");

    const [task] = await vault.readDueProviderRevocations(now);
    expect(task).toBeDefined();
    if (task === undefined) throw new Error("Missing revocation task.");
    revocationTaskIds.push(task.id);
    const raw = await redis.get(redisKey("provider-revocation", task.id));
    expect(raw).not.toBeNull();
    expect(raw).not.toContain(refreshToken);
    expect(raw).not.toContain(providerSessionId);

    const failed = await reconciler.drainProviderRevocations({
      now,
      revoke: async () => false,
    });
    expect(failed).toEqual({
      confirmed: 0,
      leaseUnavailable: false,
      retryRequired: 1,
      scanned: 1,
    });
    expect(await vault.readDueProviderRevocations(now)).toHaveLength(0);

    const succeeded = await reconciler.drainProviderRevocations({
      now: new Date(now.getTime() + 61_000),
      revoke: async (observedToken) => observedToken === refreshToken,
    });
    expect(succeeded).toEqual({
      confirmed: 1,
      leaseUnavailable: false,
      retryRequired: 0,
      scanned: 1,
    });
    expect(await redis.exists(redisKey("provider-revocation", task.id))).toBe(
      0,
    );
  });

  it("fences revocation mutation after a worker loses its lease", async () => {
    const now = new Date();
    const id = await vault.enqueueProviderRevocation({
      now,
      providerSessionId: `provider-${randomUUID()}`,
      refreshToken: `refresh-${randomUUID()}`,
    });
    revocationTaskIds.push(id);
    const task = (await vault.readDueProviderRevocations(now, 100)).find(
      (candidate) => candidate.id === id,
    );
    expect(task?.id).toBe(id);
    if (task === undefined) throw new Error("Missing fenced task.");
    const lease = await vault.acquireProviderRevocationLease();
    expect(lease).not.toBeNull();
    if (lease === null) throw new Error("Missing worker lease.");
    await vault.releaseProviderRevocationLease(lease);

    expect(
      await vault.rescheduleProviderRevocation(
        task,
        {
          attemptedAt: now,
          nextAttemptAt: new Date(now.getTime() + 60_000),
        },
        lease,
      ),
    ).toBe(false);
    expect(await redis.exists(redisKey("provider-revocation", id))).toBe(1);
    await vault.deleteProviderRevocationTask(id);
  });

  it("bounds provider retries and removes the refresh secret at terminal state", async () => {
    let now = new Date("2026-07-24T09:00:00.000Z");
    const refreshToken = `bounded-secret-${randomUUID()}`;
    const id = await vault.enqueueProviderRevocation({
      now,
      providerSessionId: `provider-${randomUUID()}`,
      refreshToken,
    });
    revocationTaskIds.push(id);

    for (let attempt = 0; attempt < 6; attempt += 1) {
      const result = await reconciler.drainProviderRevocations({
        limit: 1,
        now,
        revoke: async () => false,
      });
      expect(result.scanned).toBe(1);
      now = new Date(now.getTime() + 25 * 60 * 60 * 1_000);
    }

    expect(await redis.exists(redisKey("provider-revocation", id))).toBe(0);
    const terminal = await vault.readProviderRevocationTerminal(id);
    expect(terminal).toMatchObject({
      attemptCount: 5,
      status: "retry_required",
    });
    expect(JSON.stringify(terminal)).not.toContain(refreshToken);
  });
});
