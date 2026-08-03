import {
  CanActivate,
  ExecutionContext,
  Injectable,
  Logger,
  ServiceUnavailableException,
} from '@nestjs/common';
import {
  StagingChatLiveControl,
  StagingChatLiveControlClosedError,
} from '../../application/ports/staging-chat-live-control';

@Injectable()
export class StagingChatLiveControlGuard implements CanActivate {
  private readonly logger = new Logger(StagingChatLiveControlGuard.name);

  constructor(private readonly liveControl: StagingChatLiveControl) {}

  async canActivate(context: ExecutionContext): Promise<boolean> {
    void context;
    try {
      await this.liveControl.assertLive();
      return true;
    } catch (error) {
      const reason =
        error instanceof StagingChatLiveControlClosedError
          ? error.reason
          : 'unavailable';
      this.logger.warn(
        { control: 'authenticated-staging-chat', reason },
        'Authenticated staging Chat live control is closed.',
      );
      throw new ServiceUnavailableException({
        code: 'CHAT_LIVE_CONTROL_CLOSED',
        message: 'Chat is temporarily unavailable.',
      });
    }
  }
}
