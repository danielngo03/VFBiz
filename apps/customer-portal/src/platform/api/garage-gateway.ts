import "server-only";
import type { components } from "@vfbiz/api-client";
import {
  customerApiGet,
  customerApiRequest,
} from "@/platform/api/customer-api";

type GarageEntry = components["schemas"]["CustomerGarageEntry"];
type GarageProblem = components["schemas"]["ProblemDetails"];

export type GarageReadResult =
  | { readonly entries: readonly GarageEntry[]; readonly state: "ready" }
  | {
      readonly correlationId?: string;
      readonly state:
        | "forbidden"
        | "provider_unavailable"
        | "session_required"
        | "unexpected";
    };

export type GarageMutationResult =
  | {
      readonly entry: GarageEntry;
      readonly state: "completed";
    }
  | {
      readonly correlationId?: string;
      readonly state:
        | "conflict"
        | "forbidden"
        | "invalid"
        | "not_found"
        | "provider_unavailable"
        | "session_required"
        | "unexpected";
    };

async function readProblem(response: Response): Promise<GarageProblem | null> {
  try {
    const value: unknown = await response.json();
    if (
      value !== null &&
      typeof value === "object" &&
      typeof (value as Record<string, unknown>).status === "number" &&
      typeof (value as Record<string, unknown>).correlationId === "string"
    ) {
      return value as GarageProblem;
    }
  } catch {
    // The caller still maps the HTTP status without exposing provider payload.
  }
  return null;
}

async function failureResult(
  response: Response,
): Promise<Exclude<GarageMutationResult, { state: "completed" }>> {
  const problem = await readProblem(response);
  const correlationId =
    problem?.correlationId ??
    response.headers.get("x-correlation-id") ??
    undefined;

  if (response.status === 400 || response.status === 422) {
    return { correlationId, state: "invalid" };
  }
  if (response.status === 401) {
    return { correlationId, state: "session_required" };
  }
  if (response.status === 403) {
    return { correlationId, state: "forbidden" };
  }
  if (response.status === 404) {
    return { correlationId, state: "not_found" };
  }
  if (response.status === 409 || response.status === 412) {
    return { correlationId, state: "conflict" };
  }
  if (response.status >= 500) {
    return { correlationId, state: "provider_unavailable" };
  }
  return { correlationId, state: "unexpected" };
}

async function readEntry(response: Response): Promise<GarageMutationResult> {
  if (!response.ok) return failureResult(response);
  try {
    const entry: unknown = await response.json();
    if (isGarageEntry(entry)) return { entry, state: "completed" };
  } catch {
    // A malformed successful response is not safe to treat as completed.
  }
  return { state: "unexpected" };
}

export async function readCustomerGarage(): Promise<GarageReadResult> {
  try {
    const response = await customerApiGet("/api/v1/me/vehicles");
    if (response.ok) {
      const entries: unknown = await response.json();
      return Array.isArray(entries) && entries.every(isGarageEntry)
        ? { entries, state: "ready" }
        : { state: "unexpected" };
    }
    const failure = await failureResult(response);
    return {
      correlationId: failure.correlationId,
      state:
        failure.state === "session_required" ||
        failure.state === "forbidden" ||
        failure.state === "provider_unavailable"
          ? failure.state
          : "unexpected",
    };
  } catch {
    return { state: "provider_unavailable" };
  }
}

function isGarageEntry(value: unknown): value is GarageEntry {
  if (value === null || typeof value !== "object") return false;
  const candidate = value as Record<string, unknown>;
  return (
    typeof candidate.id === "string" &&
    typeof candidate.claimedVehicleVariantId === "string" &&
    typeof candidate.isPrimary === "boolean" &&
    typeof candidate.version === "number" &&
    typeof candidate.updatedAt === "string"
  );
}

export async function createCustomerGarageEntry(input: {
  readonly idempotencyKey: string;
  readonly isPrimary: boolean;
  readonly nickname: string | null;
  readonly variantId: string;
}): Promise<GarageMutationResult> {
  try {
    return await customerApiRequest("/api/v1/me/vehicles", {
      body: JSON.stringify({
        claimedVehicleVariantId: input.variantId,
        isPrimary: input.isPrimary,
        nickname: input.nickname,
      } satisfies components["schemas"]["CreateCustomerGarageEntry"]),
      headers: {
        "content-type": "application/json",
        "idempotency-key": input.idempotencyKey,
      },
      method: "POST",
    }).then(readEntry);
  } catch {
    return { state: "provider_unavailable" };
  }
}

export async function updateCustomerGarageEntry(input: {
  readonly entryId: string;
  readonly isPrimary?: boolean;
  readonly nickname?: string | null;
  readonly version: number;
}): Promise<GarageMutationResult> {
  const payload: components["schemas"]["UpdateCustomerGarageEntry"] = {
    ...(input.isPrimary !== undefined && { isPrimary: input.isPrimary }),
    ...(input.nickname !== undefined && { nickname: input.nickname }),
  };
  try {
    return await customerApiRequest(`/api/v1/me/vehicles/${input.entryId}`, {
      body: JSON.stringify(payload),
      headers: {
        "content-type": "application/json",
        "if-match": `"garage-${input.version}"`,
      },
      method: "PATCH",
    }).then(readEntry);
  } catch {
    return { state: "provider_unavailable" };
  }
}

export async function archiveCustomerGarageEntry(input: {
  readonly entryId: string;
  readonly version: number;
}): Promise<GarageMutationResult> {
  try {
    return await customerApiRequest(`/api/v1/me/vehicles/${input.entryId}`, {
      headers: { "if-match": `"garage-${input.version}"` },
      method: "DELETE",
    }).then(readEntry);
  } catch {
    return { state: "provider_unavailable" };
  }
}
