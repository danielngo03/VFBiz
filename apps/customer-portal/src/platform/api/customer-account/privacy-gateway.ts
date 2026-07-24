import "server-only";

import { customerApiRequest } from "@/platform/api/customer-api";
import {
  consentRecordsSchema,
  dataRequestSchema,
  dataRequestsSchema,
  type ConsentRecord,
  type ConsentWrite,
  type DataRequest,
  type DataRequestInput,
} from "./privacy-contracts";
import { parseAccountResponse } from "./response";

export { CustomerAccountApiError } from "./response";

export async function listCustomerConsents(): Promise<ConsentRecord[]> {
  return parseAccountResponse(
    await customerApiRequest("/api/v1/me/consents", { method: "GET" }),
    consentRecordsSchema,
  );
}

export async function updateCustomerConsents(
  consents: ConsentWrite[],
  idempotencyKey: string,
): Promise<ConsentRecord[]> {
  return parseAccountResponse(
    await customerApiRequest("/api/v1/me/consents", {
      body: JSON.stringify({ consents }),
      headers: {
        "content-type": "application/json",
        "idempotency-key": idempotencyKey,
      },
      method: "PUT",
    }),
    consentRecordsSchema,
  );
}

export async function listCustomerDataRequests(): Promise<DataRequest[]> {
  return parseAccountResponse(
    await customerApiRequest("/api/v1/me/data-requests", { method: "GET" }),
    dataRequestsSchema,
  );
}

export async function createCustomerDataRequest(
  input: DataRequestInput,
  idempotencyKey: string,
): Promise<DataRequest> {
  return parseAccountResponse(
    await customerApiRequest("/api/v1/me/data-requests", {
      body: JSON.stringify(input),
      headers: {
        "content-type": "application/json",
        "idempotency-key": idempotencyKey,
      },
      method: "POST",
    }),
    dataRequestSchema,
    202,
  );
}
