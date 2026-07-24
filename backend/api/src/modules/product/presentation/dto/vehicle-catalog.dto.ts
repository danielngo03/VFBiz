import { ApiProperty } from '@nestjs/swagger';

export class CatalogSourceDto {
  @ApiProperty({ example: '2026-07-23T00:00:00.000Z', format: 'date-time' })
  effectiveFrom!: Date;

  @ApiProperty({ enum: ['fresh', 'stale', 'unavailable'], example: 'fresh' })
  freshness!: 'fresh' | 'stale' | 'unavailable';

  @ApiProperty({ example: 'pim-vn-2026-07-23-r1' })
  revision!: string;

  @ApiProperty({ example: 'pim' })
  sourceId!: string;
}

export class VehicleVariantCatalogDto {
  @ApiProperty({ enum: ['announced', 'active', 'discontinued'] })
  commercialStatus!: 'announced' | 'active' | 'discontinued';

  @ApiProperty({ example: ['CCS2'], isArray: true, type: String })
  connectorStandards!: readonly string[];

  @ApiProperty({ example: 471, nullable: true })
  declaredRangeKm!: number | null;

  @ApiProperty({ example: 'AWD', nullable: true })
  drivetrain!: string | null;

  @ApiProperty({ example: 87.7, nullable: true })
  grossBatteryCapacityKwh!: number | null;

  @ApiProperty({ format: 'uuid' })
  id!: string;

  @ApiProperty({ example: 11, nullable: true })
  maximumAcChargePowerKw!: number | null;

  @ApiProperty({ example: 150, nullable: true })
  maximumDcChargePowerKw!: number | null;

  @ApiProperty({ example: 'VF 8 Plus' })
  name!: string;

  @ApiProperty({ example: 'WLTP', nullable: true })
  rangeTestStandard!: string | null;

  @ApiProperty({ example: 5, nullable: true })
  seats!: number | null;

  @ApiProperty({ example: 82, nullable: true })
  usableBatteryCapacityKwh!: number | null;

  @ApiProperty({ example: 'VF8_PLUS' })
  variantCode!: string;
}

export class VehicleModelCatalogDto {
  @ApiProperty({ example: 'VINFAST' })
  brandCode!: string;

  @ApiProperty({ example: 'suv' })
  category!: string;

  @ApiProperty({ enum: ['announced', 'active', 'discontinued'] })
  commercialStatus!: 'announced' | 'active' | 'discontinued';

  @ApiProperty({ format: 'uuid' })
  id!: string;

  @ApiProperty({ example: 'VN' })
  market!: string;

  @ApiProperty({ example: 'VF_8' })
  modelCode!: string;

  @ApiProperty({ example: 2026, nullable: true })
  modelYear!: number | null;

  @ApiProperty({ example: 'VF 8' })
  name!: string;

  @ApiProperty({ example: 'catalog-vn-2026-07-23' })
  releaseVersion!: string;

  @ApiProperty({ example: 'vf-8' })
  slug!: string;

  @ApiProperty({ type: CatalogSourceDto })
  source!: CatalogSourceDto;

  @ApiProperty({ isArray: true, type: VehicleVariantCatalogDto })
  variants!: readonly VehicleVariantCatalogDto[];
}

export class CommercialSourceDto {
  @ApiProperty({ format: 'date-time' })
  effectiveFrom!: Date;

  @ApiProperty({ format: 'date-time', nullable: true })
  expiresAt!: Date | null;

  @ApiProperty({ enum: ['fresh'] })
  freshness!: 'fresh';

  @ApiProperty({ format: 'date-time' })
  observedAt!: Date;

  @ApiProperty({ example: 'commercial-vn-2026-07-r1' })
  revision!: string;

  @ApiProperty({ example: 'erp-commercial-projection' })
  sourceId!: string;
}

export class PriceOfferDto {
  @ApiProperty({
    description:
      'Amount in the smallest currency unit, encoded as a decimal string.',
    example: '900000000',
    pattern: '^[0-9]+$',
  })
  amountMinor!: string;

  @ApiProperty({ enum: ['public', 'retail', 'fleet', 'employee'] })
  channel!: 'public' | 'retail' | 'fleet' | 'employee';

  @ApiProperty({ example: 'VND', pattern: '^[A-Z]{3}$' })
  currency!: string;

  @ApiProperty({ example: 'VN' })
  market!: string;

  @ApiProperty({ example: 'VF8-MSRP-PUBLIC' })
  offerCode!: string;

  @ApiProperty({ enum: ['msrp', 'list', 'option', 'service'] })
  priceType!: 'msrp' | 'list' | 'option' | 'service';

  @ApiProperty({ type: CommercialSourceDto })
  source!: CommercialSourceDto;

  @ApiProperty({
    enum: ['tax_inclusive', 'tax_exclusive', 'not_applicable'],
  })
  taxTreatment!: 'tax_inclusive' | 'tax_exclusive' | 'not_applicable';

  @ApiProperty({ format: 'date-time' })
  validFrom!: Date;

  @ApiProperty({ format: 'date-time', nullable: true })
  validTo!: Date | null;

  @ApiProperty({ format: 'uuid' })
  variantId!: string;
}

export class PromotionDto {
  @ApiProperty({
    description:
      'Fixed benefit in the smallest currency unit, or null for another benefit type.',
    example: '50000000',
    nullable: true,
    pattern: '^[0-9]+$',
  })
  benefitAmountMinor!: string | null;

  @ApiProperty({ example: 10, nullable: true })
  benefitPercentage!: number | null;

  @ApiProperty({
    enum: ['fixed_amount', 'percentage', 'in_kind', 'composite'],
  })
  benefitType!: 'fixed_amount' | 'percentage' | 'in_kind' | 'composite';

  @ApiProperty({ enum: ['public', 'retail', 'fleet', 'employee'] })
  channel!: 'public' | 'retail' | 'fleet' | 'employee';

  @ApiProperty({ example: 'VND', nullable: true })
  currency!: string | null;

  @ApiProperty({ example: 'JULY-PUBLIC-OFFER' })
  promotionCode!: string;

  @ApiProperty({ example: 'v1' })
  promotionVersion!: string;

  @ApiProperty({ type: CommercialSourceDto })
  source!: CommercialSourceDto;

  @ApiProperty({ enum: ['exclusive', 'stackable', 'rule_based'] })
  stackingPolicy!: 'exclusive' | 'stackable' | 'rule_based';

  @ApiProperty({ example: 'Public synthetic promotion' })
  title!: string;

  @ApiProperty({ format: 'date-time' })
  validFrom!: Date;

  @ApiProperty({ format: 'date-time', nullable: true })
  validTo!: Date | null;

  @ApiProperty({ format: 'uuid', nullable: true })
  vehicleModelId!: string | null;

  @ApiProperty({ format: 'uuid', nullable: true })
  vehicleVariantId!: string | null;
}

export class VehicleCommercialDto {
  @ApiProperty({ example: 'VN' })
  market!: string;

  @ApiProperty({ isArray: true, type: PriceOfferDto })
  priceOffers!: readonly PriceOfferDto[];

  @ApiProperty({ isArray: true, type: PromotionDto })
  promotions!: readonly PromotionDto[];

  @ApiProperty({ example: 'commercial-vn-2026-07' })
  releaseVersion!: string;
}
