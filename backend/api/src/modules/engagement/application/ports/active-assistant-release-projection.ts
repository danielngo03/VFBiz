export interface AssistantReleaseBinding {
  readonly activationEnvelopeSha256: string;
  readonly activationId: string;
  readonly effectiveAt: Date;
  readonly expiresAt: Date;
  readonly graphRevision: string;
  readonly knowledgeRevision: string;
  readonly manifestSha256: string;
  readonly pointerRevision: number;
  readonly policyRevision: string;
}

export abstract class ActiveAssistantReleaseProjection {
  abstract resolve(input: {
    now: Date;
    profile: 'authenticated_customer' | 'public_customer';
  }): Promise<AssistantReleaseBinding | null>;
}
