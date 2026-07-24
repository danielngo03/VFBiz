import { Injectable } from '@nestjs/common';
import {
  CiamSessionRevocationPort,
  type CiamSessionRevocationCommand,
  type CiamSubjectCommand,
} from '../../application/ports/ciam-session-revocation.port';

@Injectable()
export class DisabledCiamSessionRevocationAdapter extends CiamSessionRevocationPort {
  revoke(
    command: CiamSessionRevocationCommand,
  ): Promise<'manual_review_required'> {
    void command;
    return Promise.resolve('manual_review_required');
  }

  revokeAll(command: CiamSubjectCommand): Promise<'manual_review_required'> {
    void command;
    return Promise.resolve('manual_review_required');
  }

  securityStatus(command: CiamSubjectCommand): Promise<null> {
    void command;
    return Promise.resolve(null);
  }
}
