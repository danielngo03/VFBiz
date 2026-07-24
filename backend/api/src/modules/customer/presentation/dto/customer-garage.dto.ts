import {
  IsBoolean,
  IsOptional,
  IsString,
  IsUUID,
  MaxLength,
} from 'class-validator';

export class CreateCustomerGarageEntryDto {
  @IsUUID('4')
  claimedVehicleVariantId!: string;

  @IsBoolean()
  @IsOptional()
  isPrimary?: boolean;

  @IsOptional()
  @IsString()
  @MaxLength(80)
  nickname?: string | null;
}

export class UpdateCustomerGarageEntryDto {
  @IsBoolean()
  @IsOptional()
  isPrimary?: boolean;

  @IsOptional()
  @IsString()
  @MaxLength(80)
  nickname?: string | null;
}
