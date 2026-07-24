import type { components } from "@vfbiz/api-client";
import { z } from "zod";

export type ConsentRecord = components["schemas"]["ConsentRecord"];
export type ConsentWrite = components["schemas"]["ConsentWrite"];
export type DataRequest = components["schemas"]["DataRequest"];
export type DataRequestInput = components["schemas"]["DataRequestInput"];

const consentPurposeSchema = z.enum([
  "analytics",
  "marketing_email",
  "marketing_sms",
  "marketing_push",
  "personalization",
]);

const consentRecordSchema: z.ZodType<ConsentRecord> = z
  .object({
    occurredAt: z.string().datetime({ offset: true }),
    policyVersion: z.string(),
    purpose: consentPurposeSchema,
    source: z.enum([
      "customer_portal",
      "mobile",
      "operations_admin",
      "system_import",
    ]),
    state: z.enum(["granted", "withdrawn"]),
  })
  .strict();

export const consentRecordsSchema = z.array(consentRecordSchema);

export const dataRequestSchema: z.ZodType<DataRequest> = z
  .object({
    completedAt: z.string().datetime({ offset: true }).nullable(),
    id: z.string().uuid(),
    requestedAt: z.string().datetime({ offset: true }),
    status: z.enum([
      "requested",
      "processing",
      "partially_completed",
      "completed",
      "rejected",
    ]),
    type: z.enum(["export", "delete"]),
  })
  .strict();

export const dataRequestsSchema = z.array(dataRequestSchema);
