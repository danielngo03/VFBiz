import { ApiProperty } from '@nestjs/swagger';
import { IsInt, IsString, Matches, Min } from 'class-validator';

export class ApproveReleaseDto {
  @ApiProperty({ example: 'evidence://review/vehicle-catalog-2026-07-24' })
  @IsString()
  @Matches(/^[a-z][a-z0-9+.-]*:\/\/\S{1,480}$/i)
  evidenceRef!: string;

  @ApiProperty({ example: 0, minimum: 0 })
  @IsInt()
  @Min(0)
  expectedRevision!: number;
}

export class ActivateReleaseDto {
  @ApiProperty({ example: 1, minimum: 0 })
  @IsInt()
  @Min(0)
  expectedRevision!: number;
}

export class RollbackReleaseDto {
  @ApiProperty({ example: 2, minimum: 0 })
  @IsInt()
  @Min(0)
  expectedCurrentRevision!: number;

  @ApiProperty({ example: 3, minimum: 0 })
  @IsInt()
  @Min(0)
  expectedTargetRevision!: number;
}
