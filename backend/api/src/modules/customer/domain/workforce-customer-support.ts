export interface WorkforceCustomerSummary {
  readonly displayName: string | null;
  readonly garageVehicleCount: number;
  readonly id: string;
  readonly locale: string;
  readonly market: string;
  readonly status: 'active' | 'suspended' | 'deleted';
  readonly updatedAt: Date;
}

export interface WorkforceCustomerSearch {
  readonly allowedMarkets: readonly string[] | null;
  readonly limit: number;
  readonly query: string;
}

export class WorkforceCustomerSearchValidationError extends Error {
  constructor() {
    super('Customer search requires at least three non-whitespace characters.');
    this.name = 'WorkforceCustomerSearchValidationError';
  }
}

export class WorkforceCustomerAccessReasonError extends Error {
  constructor() {
    super('A meaningful customer-access reason is required.');
    this.name = 'WorkforceCustomerAccessReasonError';
  }
}
