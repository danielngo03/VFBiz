import { Injectable } from '@nestjs/common';
import { VehicleCatalogRepository } from '../ports/vehicle-catalog.repository';
import {
  VehicleCatalogIdentityResolver,
  type ResolvedVehicleCatalogIdentity,
} from '../../vehicle-catalog-identity.resolver';

@Injectable()
export class ResolveVehicleCatalogIdentityService extends VehicleCatalogIdentityResolver {
  constructor(private readonly repository: VehicleCatalogRepository) {
    super();
  }

  async resolveModel(input: {
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
  > {
    const models = await this.repository.listActive(input.market, input.now);
    if (models === null) return { kind: 'unavailable' };
    const candidate = normalize(input.candidate);
    const matches = models.filter((model) =>
      [model.modelCode, model.name, model.slug].some(
        (value) => normalize(value) === candidate,
      ),
    );
    if (matches.length !== 1) return { kind: 'not_found' };
    const model = matches[0];
    return {
      kind: 'resolved',
      value: {
        modelId: model.id,
        modelReference: model.slug,
        releaseRevision: model.releaseVersion,
        sourceRevision: model.source.revision,
      },
    };
  }
}

function normalize(value: string): string {
  return value
    .normalize('NFKC')
    .trim()
    .toLocaleLowerCase('en-US')
    .replaceAll(/[\s_-]+/g, '');
}
