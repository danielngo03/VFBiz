import { Injectable } from '@nestjs/common';
import { ControlledApplyReservationAuthorityUnavailableError } from '../../application/errors/controlled-apply-reservation.errors';
import { ControlledApplyAuthorityVerifier } from '../../application/ports/controlled-apply-authority-verifier';
import type {
  CancelControlledApplyRequest,
  VerifiedControlledApplyRequest,
} from '../../domain/controlled-apply-reservation';

/** No reservation is possible until private authority joins are wired. */
@Injectable()
export class FailClosedControlledApplyAuthorityVerifier extends ControlledApplyAuthorityVerifier {
  verifyReservation(): Promise<VerifiedControlledApplyRequest> {
    return Promise.reject(
      new ControlledApplyReservationAuthorityUnavailableError(
        'controlled-apply authority joins are not wired',
      ),
    );
  }

  verifyCancellation(): Promise<CancelControlledApplyRequest> {
    return Promise.reject(
      new ControlledApplyReservationAuthorityUnavailableError(
        'controlled-apply cancellation joins are not wired',
      ),
    );
  }
}
