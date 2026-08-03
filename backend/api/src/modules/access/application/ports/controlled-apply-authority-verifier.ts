import type {
  CancelControlledApplyRequest,
  VerifiedControlledApplyRequest,
} from '../../domain/controlled-apply-reservation';

/**
 * API-owned join boundary; callers cannot self-attest workforce authority.
 * Implementations must also fetch the exact source object generation and
 * rehash its bytes before returning the verified request.
 */
export abstract class ControlledApplyAuthorityVerifier {
  abstract verifyReservation(
    input: VerifiedControlledApplyRequest,
  ): Promise<VerifiedControlledApplyRequest>;

  abstract verifyCancellation(
    input: CancelControlledApplyRequest,
  ): Promise<CancelControlledApplyRequest>;
}
