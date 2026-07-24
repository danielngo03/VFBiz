import type { PrismaService } from '../../../../platform/database/prisma.service';
import {
  DataClassification,
  SourceApprovalState,
  VehicleCommercialStatus,
  VehicleFactGroup,
  VehicleFactSubjectType,
} from '../../../../generated/prisma/enums';
import { PrismaVehicleCatalogRepository } from './prisma-vehicle-catalog.repository';

const now = new Date('2026-07-23T12:00:00.000Z');
const source = {
  approvalEvidenceRef: 'evidence://catalog/review-1',
  approvalState: SourceApprovalState.APPROVED,
  approvedAt: new Date('2026-07-23T11:00:00.000Z'),
  approvedByRef: 'data-owner-2',
  checksum: 'a'.repeat(64),
  classification: DataClassification.PUBLIC,
  effectiveAt: new Date('2026-07-23T00:00:00.000Z'),
  expiresAt: new Date('2026-07-24T00:00:00.000Z'),
  freshnessTtlSeconds: 86_400,
  ingestedAt: new Date('2026-07-23T10:00:01.000Z'),
  licenseId: 'PROPRIETARY-VINFAST-APPROVED',
  observedAt: new Date('2026-07-23T10:00:00.000Z'),
  ownerRef: 'vehicle-data-owner',
  permittedPurposes: ['vehicle-catalog'],
  provenanceUri: 'urn:vfbiz:source:pim:release-1',
  retiredAt: null,
  submittedByRef: 'vehicle-data-operator-1',
};

const releaseId = '00000000-0000-4000-8000-000000000101';
const modelId = '00000000-0000-4000-8000-000000000102';
const variantId = '00000000-0000-4000-8000-000000000103';

const fact = (subjectType: VehicleFactSubjectType, subjectRef: string) => ({
  factGroup: VehicleFactGroup.IDENTITY_COMMERCIAL,
  sourceRevision: source,
  subjectRef,
  subjectType,
});

const release = {
  factProvenance: [
    fact(VehicleFactSubjectType.RELEASE, releaseId),
    fact(VehicleFactSubjectType.MODEL, modelId),
    fact(VehicleFactSubjectType.VARIANT, variantId),
  ],
  id: releaseId,
  market: 'VN',
  releaseVersion: 'catalog-2026-07-23',
  sourceRevision: { ...source, revision: 'pim-r1', source: 'pim' },
};

const modelRevisions = [
  {
    canonicalName: 'VF 8',
    category: 'suv',
    commercialStatus: VehicleCommercialStatus.ACTIVE,
    modelYear: 2026,
    vehicleModel: {
      brandCode: 'VINFAST',
      id: modelId,
      modelCode: 'VF_8',
      slug: 'vf-8',
      variants: [
        {
          id: variantId,
          variantCode: 'VF8-ECO',
          variantRevisions: [
            {
              canonicalName: 'VF 8 Eco',
              commercialStatus: VehicleCommercialStatus.ACTIVE,
              connectorStandards: [],
              declaredRangeKm: null,
              drivetrain: null,
              grossBatteryCapacityKwh: null,
              maximumAcChargePowerKw: null,
              maximumDcChargePowerKw: null,
              rangeTestStandard: null,
              seats: null,
              usableBatteryCapacityKwh: null,
            },
          ],
        },
      ],
    },
  },
];

function repositoryWith(catalogRelease: unknown) {
  const prisma = {
    vehicleCatalogRelease: {
      findFirst: jest.fn().mockResolvedValue(catalogRelease),
    },
    vehicleModelRevision: {
      findMany: jest.fn().mockResolvedValue(modelRevisions),
    },
  } as unknown as PrismaService;
  return new PrismaVehicleCatalogRepository(prisma);
}

describe('PrismaVehicleCatalogRepository publication defense', () => {
  it('publishes only when release, model and variant fact provenance is covered', async () => {
    await expect(
      repositoryWith(release).listActive('VN', now),
    ).resolves.toEqual([
      expect.objectContaining({
        id: modelId,
        variants: [expect.objectContaining({ id: variantId })],
      }),
    ]);
  });

  it('fails closed when required per-fact provenance is missing', async () => {
    const incomplete = {
      ...release,
      factProvenance: release.factProvenance.slice(0, 2),
    };

    await expect(
      repositoryWith(incomplete).listActive('VN', now),
    ).resolves.toBeNull();
  });

  it('fails closed when a fact source is not public', async () => {
    const restricted = {
      ...release,
      factProvenance: release.factProvenance.map((binding) => ({
        ...binding,
        sourceRevision: {
          ...binding.sourceRevision,
          classification: DataClassification.INTERNAL,
        },
      })),
    };

    await expect(
      repositoryWith(restricted).listActive('VN', now),
    ).resolves.toBeNull();
  });
});
