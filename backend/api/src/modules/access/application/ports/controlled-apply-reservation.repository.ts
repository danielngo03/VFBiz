import type {
  CancelControlledApplyRequest,
  CompleteControlledApplyRequest,
  ControlledApplyReservation,
  ControlledApplyReservationResult,
  VerifiedControlledApplyRequest,
} from '../../domain/controlled-apply-reservation';

export abstract class ControlledApplyReservationRepository {
  abstract reserve(
    input: VerifiedControlledApplyRequest,
  ): Promise<ControlledApplyReservationResult>;
  abstract complete(
    input: CompleteControlledApplyRequest,
  ): Promise<ControlledApplyReservation>;
  abstract cancel(
    input: CancelControlledApplyRequest,
  ): Promise<ControlledApplyReservation>;
}
