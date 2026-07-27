import { Injectable } from '@nestjs/common';

export type HandoffRecommendationReason =
  | 'insufficient_evidence'
  | 'policy_required'
  | 'safety_risk'
  | 'tool_unavailable';

@Injectable()
export class ConversationHandoffPolicyService {
  decide(input: {
    profile: 'authenticated_customer' | 'public_customer';
    reason: HandoffRecommendationReason;
  }): 'handoff' | 'refuse' {
    // Tool availability is an infrastructure concern, not a reason to create
    // an unbounded support case. Other explicit recommendations are eligible
    // for durable API-owned handoff in the baseline.
    if (input.reason === 'tool_unavailable') return 'refuse';
    return 'handoff';
  }
}
