import { Logger, type ExecutionContext } from '@nestjs/common';
import {
  StagingChatLiveControl,
  StagingChatLiveControlClosedError,
} from '../../application/ports/staging-chat-live-control';
import { StagingChatLiveControlGuard } from './staging-chat-live-control.guard';

function control(assertLive: () => Promise<void>): StagingChatLiveControl {
  return { assertLive };
}

describe('StagingChatLiveControlGuard', () => {
  it('performs a fresh liveness check for every request', async () => {
    const assertLive = jest.fn(() => Promise.resolve());
    const guard = new StagingChatLiveControlGuard(control(assertLive));
    const context = {} as ExecutionContext;

    await expect(guard.canActivate(context)).resolves.toBe(true);
    await expect(guard.canActivate(context)).resolves.toBe(true);
    expect(assertLive).toHaveBeenCalledTimes(2);
  });

  it.each([
    new StagingChatLiveControlClosedError('disabled'),
    new StagingChatLiveControlClosedError('mismatched'),
    new Error('redis host and credential details'),
  ])('sanitizes every closed or unavailable reason', async (failure) => {
    const warn = jest
      .spyOn(Logger.prototype, 'warn')
      .mockImplementation(() => undefined);
    const guard = new StagingChatLiveControlGuard(
      control(() => Promise.reject(failure)),
    );

    await expect(
      guard.canActivate({} as ExecutionContext),
    ).rejects.toMatchObject({
      response: {
        code: 'CHAT_LIVE_CONTROL_CLOSED',
        message: 'Chat is temporarily unavailable.',
      },
      status: 503,
    });
    expect(warn).toHaveBeenCalledWith(
      {
        control: 'authenticated-staging-chat',
        reason:
          failure instanceof StagingChatLiveControlClosedError
            ? failure.reason
            : 'unavailable',
      },
      'Authenticated staging Chat live control is closed.',
    );
    expect(JSON.stringify(warn.mock.calls)).not.toContain(
      'redis host and credential details',
    );
    warn.mockRestore();
  });
});
