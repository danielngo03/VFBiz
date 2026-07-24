export interface CustomerGarageEntryView {
  readonly claimedVehicleVariantId: string;
  readonly createdAt: Date;
  readonly id: string;
  readonly isPrimary: boolean;
  readonly nickname: string | null;
  readonly ownershipStatus: 'unverified';
  readonly source: 'imported' | 'self-reported';
  readonly status: 'active' | 'archived';
  readonly updatedAt: Date;
  readonly version: number;
}

export class CustomerGarageEntryNotFoundError extends Error {
  constructor() {
    super('Customer garage entry was not found.');
    this.name = 'CustomerGarageEntryNotFoundError';
  }
}

export class CustomerGarageVersionConflictError extends Error {
  constructor() {
    super('Customer garage entry version does not match.');
    this.name = 'CustomerGarageVersionConflictError';
  }
}

export class CustomerGarageIdempotencyConflictError extends Error {
  constructor() {
    super('Garage idempotency key was reused for another request.');
    this.name = 'CustomerGarageIdempotencyConflictError';
  }
}

export class CustomerGarageVariantUnavailableError extends Error {
  constructor() {
    super('Vehicle variant is unavailable in the active catalog.');
    this.name = 'CustomerGarageVariantUnavailableError';
  }
}

export class CustomerGaragePrimaryInvariantError extends Error {
  constructor() {
    super('A primary garage entry must be replaced or archived.');
    this.name = 'CustomerGaragePrimaryInvariantError';
  }
}

export class CustomerGarageConcurrentModificationError extends Error {
  constructor() {
    super(
      'Customer garage was modified concurrently; retry with current state.',
    );
    this.name = 'CustomerGarageConcurrentModificationError';
  }
}
