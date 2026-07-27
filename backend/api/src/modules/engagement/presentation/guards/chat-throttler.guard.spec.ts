import { resolveChatThrottleAddress } from './chat-throttler.guard';

describe('resolveChatThrottleAddress', () => {
  it('uses only the Fastify-derived client address', () => {
    const request = {
      ip: '198.51.100.40',
      ips: ['203.0.113.99', '10.0.0.4'],
    };

    expect(resolveChatThrottleAddress(request)).toBe('198.51.100.40');
  });
});
