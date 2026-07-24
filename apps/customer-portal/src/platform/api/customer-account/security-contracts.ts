import type { components } from "@vfbiz/api-client";
import { z } from "zod";

export type CustomerSession = components["schemas"]["CustomerSession"];
export type CustomerIdentitySecurity =
  components["schemas"]["CustomerIdentitySecurity"];
export type RevokeSessionResult =
  components["schemas"]["RevokeSessionResult"];
export type RevokeAllSessionsResult =
  components["schemas"]["RevokeAllSessionsResult"];

const customerSessionSchema: z.ZodType<CustomerSession> = z
  .object({
    authenticatedAt: z.string().datetime({ offset: true }),
    deviceLabel: z.string().nullable(),
    emailVerified: z.boolean().nullable(),
    expiresAt: z.string().datetime({ offset: true }),
    id: z.string().uuid(),
    isCurrent: z.boolean(),
    lastSeenAt: z.string().datetime({ offset: true }),
    mfaSatisfied: z.boolean(),
    networkHint: z.string().nullable(),
    revokedAt: z.string().datetime({ offset: true }).nullable(),
    status: z.enum(["active", "expired", "revoked"]),
    userAgentSummary: z.string().nullable(),
  })
  .strict();

export const customerSessionsSchema = z.array(customerSessionSchema);

export const identitySecuritySchema: z.ZodType<CustomerIdentitySecurity> = z
  .object({
    currentSessionMfaSatisfied: z.boolean(),
    emailVerified: z.boolean().nullable(),
    mfaConfigured: z.boolean().nullable(),
    providerStatus: z.enum(["available", "unavailable"]),
  })
  .strict();

export const revokeSessionResultSchema: z.ZodType<RevokeSessionResult> = z
  .object({
    reconciliation: z.enum([
      "confirmed",
      "manual_review_required",
      "pending",
      "retry_required",
    ]),
    session: customerSessionSchema,
  })
  .strict();

export const revokeAllSessionsResultSchema: z.ZodType<RevokeAllSessionsResult> =
  z
    .object({
      locallyRevokedCount: z.number().int().nonnegative(),
      reconciliation: z.enum([
        "confirmed",
        "manual_review_required",
        "retry_required",
      ]),
    })
    .strict();
