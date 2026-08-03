export interface ResolvedVehicleCatalogIdentity {
  readonly modelId: string;
  readonly modelReference: string;
  readonly releaseRevision: string;
  readonly sourceRevision: string;
}

/**
 * Cross-context application contract for resolving a customer-provided model
 * label against exactly one active, approved and fresh market catalog.
 */
export abstract class VehicleCatalogIdentityResolver {
  abstract resolveModel(input: {
    candidate: string;
    market: string;
    now: Date;
  }): Promise<
    | {
        readonly kind: 'resolved';
        readonly value: ResolvedVehicleCatalogIdentity;
      }
    | { readonly kind: 'not_found' }
    | { readonly kind: 'unavailable' }
  >;
}
