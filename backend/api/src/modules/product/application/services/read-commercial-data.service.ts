import { Injectable } from '@nestjs/common';
import { CommercialDataRepository } from '../ports/commercial-data.repository';
import {
  CommercialFactUnavailableError,
  type VehicleCommercialView,
} from '../../domain/commercial-facts';

@Injectable()
export class ReadCommercialDataService {
  constructor(private readonly repository: CommercialDataRepository) {}

  async getForModel(
    modelId: string,
    market: string,
    now = new Date(),
  ): Promise<VehicleCommercialView> {
    const view = await this.repository.getActiveForModel(modelId, market, now);
    if (view === null) {
      throw new CommercialFactUnavailableError(
        'no active verified commercial release',
      );
    }
    return view;
  }
}
