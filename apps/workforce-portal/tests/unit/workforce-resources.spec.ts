import {describe, expect, it} from 'vitest';
import {
  authorizationChangeRequestSchema,
  formatAuthorizationScope,
  workforceAssignmentSchema,
  workforceAuditEventSchema,
  workforceRoleSchema,
} from '@/platform/api/workforce-resources';

describe('workforce resource contracts', () => {
  it('accepts a role returned by the reviewed Workforce API contract', () => {
    const role = workforceRoleSchema.parse({
      id: '019f8d8e-5a47-7c2e-8c26-43f33039bd08',
      key: 'customer-support-reader',
      displayName: 'Nhân viên CSKH chỉ đọc',
      description: null,
      status: 'active',
      system: false,
      version: 2,
      capabilityKeys: ['customer-support.case.read'],
      createdAt: '2026-07-24T01:00:00.000Z',
      updatedAt: '2026-07-24T02:00:00.000Z',
    });

    expect(role.capabilityKeys).toEqual(['customer-support.case.read']);
  });

  it('strips unknown fields so token material cannot cross the view contract', () => {
    const assignment = workforceAssignmentSchema.parse({
      id: '019f8d8e-5a47-7c2e-8c26-43f33039bd08',
      identitySubjectId: '019f8d8e-5a47-7c2e-8c26-43f33039bd09',
      roleId: '019f8d8e-5a47-7c2e-8c26-43f33039bd10',
      roleKey: 'auditor',
      status: 'active',
      effectiveAt: '2026-07-24T01:00:00.000Z',
      reason: 'Synthetic test assignment',
      version: 1,
      scopes: [{type: 'global', ref: 'global'}],
      accessToken: 'must-never-reach-the-view',
    });

    expect(assignment).not.toHaveProperty('accessToken');
  });

  it('keeps approval payload opaque and validates its surrounding metadata', () => {
    const request = authorizationChangeRequestSchema.parse({
      id: '019f8d8e-5a47-7c2e-8c26-43f33039bd08',
      requestType: 'create-privileged-assignment',
      status: 'pending',
      riskTier: 'privileged',
      requesterRef: 'workforce-subject:test',
      targetType: 'workforce-subject',
      targetRef: '019f8d8e-5a47-7c2e-8c26-43f33039bd09',
      reason: 'Synthetic approval scenario',
      payload: {opaque: true},
      expiresAt: '2026-07-25T01:00:00.000Z',
    });

    expect(request.status).toBe('pending');
  });

  it('validates minimized audit events and strips unreviewed payloads', () => {
    const event = workforceAuditEventSchema.parse({
      id: '019f8d8e-5a47-7c2e-8c26-43f33039bd08',
      actorRef: null,
      action: 'authorization.role.read',
      resourceType: 'workforce-role',
      resourceId: null,
      outcome: 'success',
      correlationId: '019f8d8e-5a47-7c2e-8c26-43f33039bd09',
      occurredAt: '2026-07-24T01:00:00.000Z',
      rawPayload: {secret: true},
    });

    expect(event).not.toHaveProperty('rawPayload');
  });

  it('formats organizational scope without inventing display names', () => {
    expect(formatAuthorizationScope({
      type: 'showroom',
      ref: 'showroom-hn-01',
    })).toBe('Showroom: showroom-hn-01');
  });
});
