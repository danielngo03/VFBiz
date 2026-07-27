import { createHash } from 'node:crypto';
import type { ConversationContentProtectionContextV1 } from '../../../../platform/security/conversation-content-cipher';
import type { ConversationAccessScope } from '../../domain/runtime/conversation-runtime';

export function conversationContentContext(
  accessScope: ConversationAccessScope,
  aggregateId: string,
  recordId: string,
  field: string,
): ConversationContentProtectionContextV1 {
  const canonicalOwner =
    accessScope.kind === 'public_capability'
      ? ['public_capability', accessScope.capabilityHash]
      : ['authenticated_customer', accessScope.issuer, accessScope.subject];
  return {
    aggregateId,
    field,
    ownerId: createHash('sha256')
      .update(JSON.stringify(canonicalOwner), 'utf8')
      .digest('hex'),
    recordId,
    securityDomain: 'customer-conversation',
    version: 1,
  };
}
