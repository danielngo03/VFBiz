import "server-only";
import type { components } from "@vfbiz/api-client";
import { cache } from "react";
import { createPublicApiClient } from "@/platform/api/public-api-client";
import { readCustomerPortalEnvironment } from "@/platform/config/environment";

export type ApprovedVehicleModel =
  components["schemas"]["VehicleModelProjection"];

export type ApprovedCatalogSnapshot =
  | {
      readonly models: readonly ApprovedVehicleModel[];
      readonly state: "fresh";
    }
  | {
      readonly models: readonly ApprovedVehicleModel[];
      readonly state: "stale";
    }
  | {
      readonly models: readonly [];
      readonly state: "unavailable";
    };

async function listApprovedVehicleModels(): Promise<
  readonly ApprovedVehicleModel[]
> {
  const environment = readCustomerPortalEnvironment();
  const client = createPublicApiClient(environment.CUSTOMER_API_BASE_URL);
  const { data, error, response } = await client.GET(
    "/api/v1/vehicles/models",
    {
      params: { query: { market: "VN" } },
    },
  );

  if (!response.ok || error !== undefined || data === undefined) {
    throw new Error("approved_vehicle_catalog_unavailable");
  }

  return data;
}

async function readApprovedVehicleCatalog(): Promise<ApprovedCatalogSnapshot> {
  try {
    const models = await listApprovedVehicleModels();
    if (models.some((model) => model.source.freshness !== "fresh")) {
      return { models, state: "stale" };
    }
    return { models, state: "fresh" };
  } catch {
    return { models: [], state: "unavailable" };
  }
}

export const loadApprovedVehicleCatalog = cache(readApprovedVehicleCatalog);

export function isApprovedVariant(
  models: readonly ApprovedVehicleModel[],
  variantId: string,
): boolean {
  return models.some(
    (model) =>
      model.commercialStatus === "active" &&
      model.source.freshness === "fresh" &&
      model.variants.some(
        (variant) =>
          variant.id === variantId && variant.commercialStatus === "active",
      ),
  );
}
