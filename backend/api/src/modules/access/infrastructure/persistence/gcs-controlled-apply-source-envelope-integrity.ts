import { ControlledApplySourceEnvelopeIntegrity } from '../../application/ports/controlled-apply-source-envelope-integrity';
import type { ControlledApplySourceEnvelopeReader } from '../../application/ports/controlled-apply-source-envelope-reader';
import type { VerifiedControlledApplyRequest } from '../../domain/controlled-apply-reservation';
import { assertExactSourceEnvelopeIntegrity } from './exact-source-envelope-integrity';

/** Infrastructure adapter for the application source-integrity port. */
export class GcsControlledApplySourceEnvelopeIntegrity extends ControlledApplySourceEnvelopeIntegrity {
  constructor(private readonly reader: ControlledApplySourceEnvelopeReader) {
    super();
  }

  assertExact(input: VerifiedControlledApplyRequest): Promise<void> {
    return assertExactSourceEnvelopeIntegrity(this.reader, input);
  }
}
