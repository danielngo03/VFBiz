import { Type } from 'class-transformer';
import {
  ArrayMaxSize,
  ArrayMinSize,
  IsArray,
  IsDateString,
  IsIn,
  IsInt,
  IsObject,
  IsOptional,
  IsString,
  Length,
  Matches,
  Max,
  Min,
  ValidateNested,
} from 'class-validator';
import { WORKFORCE_SCOPE_TYPES } from '../domain/workforce-authorization';

export class CreateWorkforceRoleDto {
  @IsString()
  @Matches(/^[a-z][a-z0-9-]{0,79}$/)
  key!: string;

  @IsString()
  @Length(1, 160)
  displayName!: string;

  @IsOptional()
  @IsString()
  @Length(1, 500)
  description?: string;
}

export class UpdateWorkforceRoleDto {
  @IsInt()
  @Max(2_147_483_647)
  @Min(1)
  expectedVersion!: number;

  @IsOptional()
  @IsString()
  @Length(1, 160)
  displayName?: string;

  @IsOptional()
  @IsString()
  @Length(1, 500)
  description?: string | null;
}

export class ReplaceRoleCapabilitiesDto {
  @IsInt()
  @Max(2_147_483_647)
  @Min(1)
  expectedVersion!: number;

  @ArrayMaxSize(100)
  @IsArray()
  @IsString({ each: true })
  @Matches(/^[a-z][a-z0-9-]*(?:\.[a-z][a-z0-9-]*){2,3}$/, {
    each: true,
  })
  capabilityKeys!: string[];
}

export class AssignmentScopeDto {
  @IsIn(WORKFORCE_SCOPE_TYPES)
  type!: (typeof WORKFORCE_SCOPE_TYPES)[number];

  @IsString()
  @Length(1, 160)
  ref!: string;
}

export class CreateWorkforceAssignmentDto {
  @IsString()
  @Matches(/^[0-9a-f-]{36}$/i)
  identitySubjectId!: string;

  @IsString()
  @Matches(/^[0-9a-f-]{36}$/i)
  roleId!: string;

  @IsDateString()
  effectiveAt!: string;

  @IsOptional()
  @IsDateString()
  expiresAt?: string;

  @IsString()
  @Length(8, 500)
  reason!: string;

  @ArrayMaxSize(20)
  @ArrayMinSize(1)
  @Type(() => AssignmentScopeDto)
  @ValidateNested({ each: true })
  scopes!: AssignmentScopeDto[];
}

export class VersionedMutationDto {
  @IsInt()
  @Max(2_147_483_647)
  @Min(1)
  expectedVersion!: number;
}

export class CreateAuthorizationChangeRequestDto {
  @IsIn([
    'replace-role-capabilities',
    'disable-role',
    'create-privileged-assignment',
  ])
  requestType!:
    | 'replace-role-capabilities'
    | 'disable-role'
    | 'create-privileged-assignment';

  @IsIn(['privileged'])
  riskTier!: 'privileged';

  @IsIn(['workforce-role', 'workforce-subject'])
  targetType!: 'workforce-role' | 'workforce-subject';

  @IsString()
  @Matches(/^[0-9a-f-]{36}$/i)
  targetRef!: string;

  @IsString()
  @Length(8, 500)
  reason!: string;

  @IsObject()
  payload!: Record<string, unknown>;
}

export class DecideAuthorizationChangeRequestDto {
  @IsString()
  @Length(1, 512)
  evidenceRef!: string;

  @IsOptional()
  @IsString()
  @Length(1, 500)
  reason?: string;
}
