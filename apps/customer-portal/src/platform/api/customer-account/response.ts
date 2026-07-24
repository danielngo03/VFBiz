import "server-only";

import type { z } from "zod";

interface ProblemDetails {
  readonly code?: string;
}

export class CustomerAccountApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    readonly correlationId: string | null,
  ) {
    super(`Customer account API request failed with ${status} (${code}).`);
    this.name = "CustomerAccountApiError";
  }
}

async function readProblem(response: Response): Promise<ProblemDetails> {
  if (!response.headers.get("content-type")?.includes("json")) return {};
  try {
    return (await response.json()) as ProblemDetails;
  } catch {
    return {};
  }
}

export async function parseAccountResponse<T>(
  response: Response,
  schema: z.ZodType<T>,
  acceptedStatus = 200,
): Promise<T> {
  if (response.status !== acceptedStatus) {
    const problem = await readProblem(response);
    throw new CustomerAccountApiError(
      response.status,
      problem.code ?? "UPSTREAM_REQUEST_FAILED",
      response.headers.get("x-correlation-id"),
    );
  }

  try {
    return schema.parse(await response.json());
  } catch {
    throw new CustomerAccountApiError(
      502,
      "UPSTREAM_RESPONSE_INVALID",
      response.headers.get("x-correlation-id"),
    );
  }
}
