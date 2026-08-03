import { Injectable } from '@nestjs/common';
import {
  assertCancellationEvidence,
  assertReceipt,
  assertVerifiedControlledApplyRequest,
  type CancelControlledApplyRequest,
  type CompleteControlledApplyRequest,
  type VerifiedControlledApplyRequest,
} from '../../domain/controlled-apply-reservation';
import { ControlledApplyReservationRepository } from '../ports/controlled-apply-reservation.repository';
import { ControlledApplyAuthorityVerifier } from '../ports/controlled-apply-authority-verifier';

/** Internal-only boundary for broker integration; no controller exposes this service. */
@Injectable()
export class ControlledApplyReservationFacade {
  constructor(
    private readonly repository: ControlledApplyReservationRepository,
    private readonly authorityVerifier: ControlledApplyAuthorityVerifier,
  ) {}

  async reserve(input: VerifiedControlledApplyRequest) {
    const verified = await this.authorityVerifier.verifyReservation(input);
    assertVerifiedControlledApplyRequest(verified);
    return this.repository.reserve(verified);
  }

  complete(input: CompleteControlledApplyRequest) {
    assertReceipt(input.completionReceiptSha256, 'completion receipt');
    return this.repository.complete(input);
  }

  async cancel(input: CancelControlledApplyRequest) {
    const verified = await this.authorityVerifier.verifyCancellation(input);
    assertReceipt(verified.cancellationReceiptSha256, 'cancellation receipt');
    assertCancellationEvidence(verified.evidence);
    return this.repository.cancel(verified);
  }
}
