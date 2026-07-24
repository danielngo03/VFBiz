import {
  buildConversationCapabilityCookie,
  readConversationCapabilityCookie,
} from './conversation-capability-cookie';

describe('conversation capability cookie', () => {
  it('sets an opaque capability in a secure HttpOnly host cookie', () => {
    expect(
      buildConversationCapabilityCookie(
        '8e5aeae2-2f47-48e4-91a2-e9e41f7349fb',
        'opaque-capability',
        1800,
      ),
    ).toBe(
      '__Host-vfbiz_chat=8e5aeae2-2f47-48e4-91a2-e9e41f7349fb.opaque-capability; Max-Age=1800; Path=/; HttpOnly; Secure; SameSite=Lax',
    );
  });

  it('returns a capability only when the cookie is bound to the requested session', () => {
    const cookie =
      'theme=light; __Host-vfbiz_chat=8e5aeae2-2f47-48e4-91a2-e9e41f7349fb.opaque-capability';

    expect(
      readConversationCapabilityCookie(
        cookie,
        '8e5aeae2-2f47-48e4-91a2-e9e41f7349fb',
      ),
    ).toBe('opaque-capability');
    expect(
      readConversationCapabilityCookie(
        cookie,
        '664aa870-1ae6-457f-9e36-b7853a2ab77f',
      ),
    ).toBeNull();
  });
});
