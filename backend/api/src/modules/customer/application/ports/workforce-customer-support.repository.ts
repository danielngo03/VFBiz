import type {
  WorkforceCustomerSearch,
  WorkforceCustomerSummary,
} from '../../domain/workforce-customer-support';

export interface SearchWorkforceCustomersInput extends WorkforceCustomerSearch {
  readonly actorRef: string;
  readonly correlationId: string;
  readonly reason: string;
}

export abstract class WorkforceCustomerSupportRepository {
  abstract search(
    input: SearchWorkforceCustomersInput,
  ): Promise<readonly WorkforceCustomerSummary[]>;
}
