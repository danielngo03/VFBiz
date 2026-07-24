import { Type } from 'class-transformer';
import { ApiProperty } from '@nestjs/swagger';
import {
  ArrayMaxSize,
  ArrayMinSize,
  IsArray,
  IsBoolean,
  IsIn,
  IsOptional,
  IsString,
  Length,
  Matches,
  MaxLength,
  ValidateNested,
} from 'class-validator';
import {
  CONSENT_PURPOSES,
  CUSTOMER_LOCALES,
  CUSTOMER_MARKETS,
} from '../../domain/customer-account';

export class CommunicationPreferencesDto {
  @IsBoolean()
  @IsOptional()
  email?: boolean;

  @IsBoolean()
  @IsOptional()
  push?: boolean;

  @IsBoolean()
  @IsOptional()
  sms?: boolean;
}

export class UpdateCustomerProfileDto {
  @IsOptional()
  @IsString()
  @MaxLength(120)
  displayName?: string | null;

  @IsIn(CUSTOMER_LOCALES)
  @IsOptional()
  locale?: 'vi' | 'en';

  @IsIn(CUSTOMER_MARKETS)
  @IsOptional()
  market?: 'VN';

  @IsOptional()
  @Type(() => CommunicationPreferencesDto)
  @ValidateNested()
  communicationPreferences?: CommunicationPreferencesDto;

  @IsOptional()
  @IsString()
  @Length(1, 64)
  @Matches(/^[A-Za-z_]+(?:\/[A-Za-z0-9_+-]+)+$/)
  timezone?: string;
}

export class ConsentCommandDto {
  @IsString()
  @Length(1, 80)
  policyVersion!: string;

  @IsIn(CONSENT_PURPOSES)
  purpose!: (typeof CONSENT_PURPOSES)[number];

  @IsIn(['granted', 'withdrawn'])
  state!: 'granted' | 'withdrawn';
}

export class UpdateConsentsDto {
  @ArrayMaxSize(CONSENT_PURPOSES.length)
  @ArrayMinSize(1)
  @IsArray()
  @Type(() => ConsentCommandDto)
  @ValidateNested({ each: true })
  consents!: ConsentCommandDto[];
}

export class CreateCustomerDataRequestDto {
  @IsIn(['export', 'delete'])
  type!: 'export' | 'delete';
}

export class CustomerDataRequestResponseDto {
  @ApiProperty({
    example: 'caa38420-305d-4cb5-a1e9-cdfdd08ea421',
    format: 'uuid',
  })
  id!: string;

  @ApiProperty({ enum: ['export', 'delete'] })
  type!: 'export' | 'delete';

  @ApiProperty({
    enum: [
      'requested',
      'processing',
      'partially_completed',
      'completed',
      'rejected',
    ],
  })
  status!:
    | 'requested'
    | 'processing'
    | 'partially_completed'
    | 'completed'
    | 'rejected';

  @ApiProperty({ format: 'date-time', type: String })
  requestedAt!: Date;

  @ApiProperty({ format: 'date-time', nullable: true, type: String })
  completedAt!: Date | null;
}
