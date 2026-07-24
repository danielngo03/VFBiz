import "server-only";
import { randomUUID } from "node:crypto";
import type { OpaqueCustomerSessionId } from "./contracts";
import {
  customerSessionKey,
  customerSessionRedis,
} from "./redis-vault-runtime";

const REFRESH_LEASE_MILLISECONDS = 10_000;
const BACKCHANNEL_LOGOUT_LEASE_MILLISECONDS = 30_000;
const BACKCHANNEL_LOGOUT_REPLAY_TTL_SECONDS = 600;

export type BackchannelLogoutClaim =
  | { readonly state: "acquired"; readonly token: string }
  | { readonly state: "completed" }
  | { readonly state: "in_progress" };

export async function beginBackchannelLogoutToken(
  jti: string,
): Promise<BackchannelLogoutClaim> {
  if (
    (await customerSessionRedis().exists(
      customerSessionKey("backchannel-logout", jti),
    )) === 1
  ) {
    return { state: "completed" };
  }
  const token = randomUUID();
  const acquired = await customerSessionRedis().set(
    customerSessionKey("backchannel-logout-pending", jti),
    token,
    "PX",
    BACKCHANNEL_LOGOUT_LEASE_MILLISECONDS,
    "NX",
  );
  return acquired === "OK"
    ? { state: "acquired", token }
    : { state: "in_progress" };
}

export async function completeBackchannelLogoutToken(
  jti: string,
  token: string,
): Promise<boolean> {
  const result = await customerSessionRedis().eval(
    `
      if redis.call("get", KEYS[1]) ~= ARGV[1] then return 0 end
      redis.call("set", KEYS[2], "1", "EX", ARGV[2])
      redis.call("del", KEYS[1])
      return 1
    `,
    2,
    customerSessionKey("backchannel-logout-pending", jti),
    customerSessionKey("backchannel-logout", jti),
    token,
    String(BACKCHANNEL_LOGOUT_REPLAY_TTL_SECONDS),
  );
  return Number(result) === 1;
}

export async function releaseBackchannelLogoutToken(
  jti: string,
  token: string,
): Promise<void> {
  await customerSessionRedis().eval(
    'if redis.call("get", KEYS[1]) == ARGV[1] then return redis.call("del", KEYS[1]) end return 0',
    1,
    customerSessionKey("backchannel-logout-pending", jti),
    token,
  );
}

export async function acquireRefreshLease(
  id: OpaqueCustomerSessionId,
): Promise<string | null> {
  const lease = randomUUID();
  const result = await customerSessionRedis().set(
    customerSessionKey("refresh-lease", id),
    lease,
    "PX",
    REFRESH_LEASE_MILLISECONDS,
    "NX",
  );
  return result === "OK" ? lease : null;
}

export async function releaseRefreshLease(
  id: OpaqueCustomerSessionId,
  lease: string,
): Promise<void> {
  await customerSessionRedis().eval(
    'if redis.call("get", KEYS[1]) == ARGV[1] then return redis.call("del", KEYS[1]) end return 0',
    1,
    customerSessionKey("refresh-lease", id),
    lease,
  );
}
