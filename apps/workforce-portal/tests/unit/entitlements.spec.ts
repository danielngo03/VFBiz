import {describe, expect, it} from 'vitest';
import {
  hasAllCapabilities,
  workforceEntitlementsSchema,
} from '@/platform/api/entitlements';
import {visibleNavigation} from '@/features/authorization/model/navigation';

const entitlements = workforceEntitlementsSchema.parse({
  identitySubjectId: '019f8d8e-5a47-7c2e-8c26-43f33039bd08',
  revision: 'revision-synthetic-1',
  capabilities: [
    {
      key: 'authorization.role.read',
      riskTier: 'sensitive',
      scopes: [{type: 'global', ref: 'global'}],
    },
    {
      key: 'audit.event.read',
      riskTier: 'sensitive',
      scopes: [{type: 'global', ref: 'global'}],
    },
  ],
});

describe('workforce entitlements', () => {
  it('shows only navigation backed by API-derived capabilities', () => {
    expect(visibleNavigation(entitlements).map(({href}) => href)).toEqual([
      '/authorization/roles',
      '/audit',
    ]);
  });

  it('fails closed when a required capability is missing', () => {
    expect(hasAllCapabilities(
      entitlements,
      ['authorization.assignment.read'],
    )).toBe(false);
  });

  it('rejects token material and unknown fields in the browser-facing view', () => {
    expect(() => workforceEntitlementsSchema.parse({
      ...entitlements,
      accessToken: 'must-not-reach-the-browser',
    })).toThrow();
  });

  it('rejects wildcard and malformed capabilities', () => {
    expect(() => workforceEntitlementsSchema.parse({
      ...entitlements,
      capabilities: [
        {
          key: '*',
          riskTier: 'standard',
          scopes: [{type: 'global', ref: 'global'}],
        },
      ],
    })).toThrow();
  });
});
