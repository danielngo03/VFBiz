import type { VehicleCommercialView } from '../../domain/commercial-facts';

export abstract class CommercialDataRepository {
  abstract getActiveForModel(
    modelId: string,
    market: string,
    now: Date,
  ): Promise<VehicleCommercialView | null>;
}
