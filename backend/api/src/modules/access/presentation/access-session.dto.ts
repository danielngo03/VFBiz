import { ApiProperty } from '@nestjs/swagger';

export class AccessSessionResponseDto {
  @ApiProperty({ format: 'uuid' })
  id!: string;

  @ApiProperty()
  isCurrent!: boolean;

  @ApiProperty({ enum: ['active', 'expired', 'revoked'] })
  status!: 'active' | 'expired' | 'revoked';

  @ApiProperty({ format: 'date-time', type: String })
  authenticatedAt!: Date;

  @ApiProperty({ format: 'date-time', type: String })
  lastSeenAt!: Date;

  @ApiProperty({ format: 'date-time', type: String })
  expiresAt!: Date;

  @ApiProperty({ format: 'date-time', nullable: true, type: String })
  revokedAt!: Date | null;

  @ApiProperty({ nullable: true, type: String })
  deviceLabel!: string | null;

  @ApiProperty({
    description:
      'Privacy-minimized network prefix observed for this session, never a raw IP address.',
    nullable: true,
    type: String,
  })
  networkHint!: string | null;

  @ApiProperty({
    description: 'Sanitized user-agent summary captured at authentication.',
    nullable: true,
    type: String,
  })
  userAgentSummary!: string | null;

  @ApiProperty({
    description:
      'Whether multi-factor authentication was observed for this session.',
  })
  mfaSatisfied!: boolean;

  @ApiProperty({
    description:
      'Verified email state issued by CIAM, or null when the provider omitted the claim.',
    nullable: true,
    type: Boolean,
  })
  emailVerified!: boolean | null;
}

export class RevokeSessionResponseDto {
  @ApiProperty({
    enum: ['confirmed', 'manual_review_required', 'pending', 'retry_required'],
  })
  reconciliation!:
    'confirmed' | 'manual_review_required' | 'pending' | 'retry_required';

  @ApiProperty({ type: AccessSessionResponseDto })
  session!: AccessSessionResponseDto;
}

export class RevokeAllSessionsResponseDto {
  @ApiProperty({ minimum: 0 })
  locallyRevokedCount!: number;

  @ApiProperty({
    enum: ['confirmed', 'manual_review_required', 'retry_required'],
  })
  reconciliation!: 'confirmed' | 'manual_review_required' | 'retry_required';
}

export class CustomerIdentitySecurityResponseDto {
  @ApiProperty()
  currentSessionMfaSatisfied!: boolean;

  @ApiProperty({ nullable: true, type: Boolean })
  emailVerified!: boolean | null;

  @ApiProperty({
    description:
      'Null when the protected CIAM administration bridge is unavailable.',
    nullable: true,
    type: Boolean,
  })
  mfaConfigured!: boolean | null;

  @ApiProperty({ enum: ['available', 'unavailable'] })
  providerStatus!: 'available' | 'unavailable';
}
