import type { components } from "@vfbiz/api-client";
import { z } from "zod";

export type CustomerProfile = components["schemas"]["CustomerProfile"];
export type CustomerProfilePatch =
  components["schemas"]["CustomerProfilePatch"];

const communicationPreferencesSchema = z
  .object({
    email: z.boolean(),
    push: z.boolean(),
    sms: z.boolean(),
  })
  .strict();

export const customerProfileSchema: z.ZodType<CustomerProfile> = z
  .object({
    communicationPreferences: communicationPreferencesSchema,
    displayName: z.string().max(120).nullable().optional(),
    locale: z.enum(["vi", "en"]),
    market: z.literal("VN"),
    timezone: z.string().min(1).max(64),
    updatedAt: z.string().datetime({ offset: true }),
    version: z.number().int().positive(),
  })
  .strict();

export const profileEtagSchema = z
  .string()
  .regex(/^(?:W\/)?"profile-\d+"$/u);
