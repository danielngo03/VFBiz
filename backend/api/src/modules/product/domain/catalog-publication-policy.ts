import {
  DataClassification,
  SourceApprovalState,
  VehicleFactGroup,
  VehicleFactSubjectType,
} from '../../../generated/prisma/enums';
import {
  assertSourceRevisionEligible,
  type SourceRevisionEvidence,
} from '../../../platform/provenance/source-revision-policy';

export interface CatalogPublicationSource {
  readonly approvalEvidenceRef: string | null;
  readonly approvalState: SourceApprovalState;
  readonly approvedAt: Date | null;
  readonly approvedByRef: string | null;
  readonly checksum: string;
  readonly classification: DataClassification;
  readonly effectiveAt: Date;
  readonly expiresAt: Date | null;
  readonly freshnessTtlSeconds: number;
  readonly ingestedAt: Date;
  readonly licenseId: string;
  readonly observedAt: Date;
  readonly ownerRef: string;
  readonly permittedPurposes: readonly string[];
  readonly provenanceUri: string;
  readonly retiredAt: Date | null;
  readonly submittedByRef: string;
}

export interface CatalogPublicationBinding {
  readonly factGroup: VehicleFactGroup;
  readonly sourceRevision: CatalogPublicationSource;
  readonly subjectRef: string;
  readonly subjectType: VehicleFactSubjectType;
}

export interface CatalogPublicationVariant {
  readonly id: string;
  readonly requiredGroups: ReadonlySet<VehicleFactGroup>;
}

export interface CatalogVariantFactShape {
  readonly connectorStandards: readonly string[];
  readonly declaredRangeKm: object | null;
  readonly drivetrain: string | null;
  readonly grossBatteryCapacityKwh: object | null;
  readonly maximumAcChargePowerKw: object | null;
  readonly maximumDcChargePowerKw: object | null;
  readonly seats: number | null;
  readonly usableBatteryCapacityKwh: object | null;
}

export class CatalogProvenanceError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'CatalogProvenanceError';
  }
}

export function assertPublishableCatalogSource(
  source: CatalogPublicationSource,
  now: Date,
): void {
  const evidence: SourceRevisionEvidence = {
    ...source,
    approvalState: source.approvalState.toLowerCase() as
      'approved' | 'pending' | 'rejected' | 'retired',
    classification: source.classification.toLowerCase() as
      'public' | 'internal' | 'confidential' | 'restricted',
  };
  assertSourceRevisionEligible(evidence, 'vehicle-catalog', now);
}

export function requiredVariantFactGroups(
  variant: CatalogVariantFactShape,
): ReadonlySet<VehicleFactGroup> {
  const requiredGroups = new Set<VehicleFactGroup>([
    VehicleFactGroup.IDENTITY_COMMERCIAL,
  ]);
  if (variant.seats !== null || variant.drivetrain !== null) {
    requiredGroups.add(VehicleFactGroup.TECHNICAL_HOMOLOGATION);
  }
  if (
    variant.grossBatteryCapacityKwh !== null ||
    variant.usableBatteryCapacityKwh !== null ||
    variant.declaredRangeKm !== null ||
    variant.maximumAcChargePowerKw !== null ||
    variant.maximumDcChargePowerKw !== null
  ) {
    requiredGroups.add(VehicleFactGroup.BATTERY_RANGE_CHARGING);
  }
  if (variant.connectorStandards.length > 0) {
    requiredGroups.add(VehicleFactGroup.OPTIONS_COMPATIBILITY);
  }
  return requiredGroups;
}

function provenanceKey(
  subjectType: VehicleFactSubjectType,
  subjectRef: string,
  factGroup: VehicleFactGroup,
): string {
  return `${subjectType}:${subjectRef}:${factGroup}`;
}

export function assertCatalogFactProvenance(
  releaseId: string,
  modelIds: ReadonlySet<string>,
  variants: readonly CatalogPublicationVariant[],
  bindings: readonly CatalogPublicationBinding[],
  now: Date,
): void {
  const variantIds = new Set(variants.map((variant) => variant.id));
  const coverage = new Set<string>();

  for (const binding of bindings) {
    const belongsToRelease =
      (binding.subjectType === VehicleFactSubjectType.RELEASE &&
        binding.subjectRef === releaseId) ||
      (binding.subjectType === VehicleFactSubjectType.MODEL &&
        modelIds.has(binding.subjectRef)) ||
      (binding.subjectType === VehicleFactSubjectType.VARIANT &&
        variantIds.has(binding.subjectRef));
    if (!belongsToRelease) {
      throw new CatalogProvenanceError('Fact binding is outside the release.');
    }
    assertPublishableCatalogSource(binding.sourceRevision, now);
    coverage.add(
      provenanceKey(binding.subjectType, binding.subjectRef, binding.factGroup),
    );
  }

  const required = [
    provenanceKey(
      VehicleFactSubjectType.RELEASE,
      releaseId,
      VehicleFactGroup.IDENTITY_COMMERCIAL,
    ),
    ...[...modelIds].map((modelId) =>
      provenanceKey(
        VehicleFactSubjectType.MODEL,
        modelId,
        VehicleFactGroup.IDENTITY_COMMERCIAL,
      ),
    ),
    ...variants.flatMap((variant) =>
      [...variant.requiredGroups].map((group) =>
        provenanceKey(VehicleFactSubjectType.VARIANT, variant.id, group),
      ),
    ),
  ];
  if (required.some((key) => !coverage.has(key))) {
    throw new CatalogProvenanceError('Required fact provenance is missing.');
  }
}
