import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { join, resolve } from 'node:path';

const prismaRoot = resolve(__dirname, '../../prisma');
const modelRoot = join(prismaRoot, 'models');
const expectedModelFiles = [
  'access.prisma',
  'commerce.prisma',
  'customer.prisma',
  'engagement.prisma',
  'mobility.prisma',
  'operations.prisma',
  'ownership.prisma',
  'platform.prisma',
  'product.prisma',
  'sales.prisma',
] as const;

describe('Prisma schema ownership', () => {
  it('has one declarative model file per durable context plus platform', () => {
    expect(existsSync(join(prismaRoot, 'schema.prisma'))).toBe(true);
    expect(readdirSync(modelRoot).sort()).toEqual([...expectedModelFiles]);
  });

  it('declares datasource and generator only in the schema root', () => {
    const root = readFileSync(join(prismaRoot, 'schema.prisma'), 'utf8');
    expect(root).toContain('generator client');
    expect(root).toContain('moduleFormat = "cjs"');
    expect(root).toContain('datasource db');

    for (const file of expectedModelFiles) {
      const content = readFileSync(join(modelRoot, file), 'utf8');
      expect(content).not.toMatch(/\b(generator|datasource)\s+\w+\s*\{/);
    }
  });

  it('models account, vehicle, trip and governed chat lifecycles explicitly', () => {
    const customer = readFileSync(join(modelRoot, 'customer.prisma'), 'utf8');
    const mobility = readFileSync(join(modelRoot, 'mobility.prisma'), 'utf8');
    const product = readFileSync(join(modelRoot, 'product.prisma'), 'utf8');
    const engagement = readFileSync(
      join(modelRoot, 'engagement.prisma'),
      'utf8',
    );
    const operations = readFileSync(
      join(modelRoot, 'operations.prisma'),
      'utf8',
    );

    expect(customer).toContain('model CustomerDataRequest');
    expect(customer).toContain('enum CustomerProfileStatus');
    expect(customer).toContain('communicationEmail');
    expect(customer).toContain('idempotencyKeyHash');
    expect(customer).toContain(
      '@@unique([customerProfileId, requestType, idempotencyKeyHash], map: "customer_data_request_idempotency_key")',
    );
    expect(product).toContain('model VehicleCatalogRelease');
    expect(product).toContain('model VehicleModelRevision');
    expect(product).toContain('model VehicleVariantRevision');
    expect(product).toContain('specificationSchemaVersion');
    expect(customer).toContain('model CustomerGarageEntry');
    expect(customer).toContain('claimedVehicleVariantId');
    expect(customer).toContain(
      '@@unique([customerProfileId, createIdempotencyKeyHash], map: "customer_garage_entry_create_idempotency_key")',
    );
    expect(customer).not.toContain('vinTokenRef');
    expect(customer).not.toContain('maskedVin');
    expect(customer).not.toContain('verificationRequestedAt');
    expect(mobility).toContain('algorithmRevision');
    expect(mobility).toContain('cachePolicy');
    expect(mobility).toContain('privacyClassification');
    expect(mobility).toContain('providerPayloadStored');
    expect(mobility).toContain('Unsupported("geography(Point,4326)")');
    expect(engagement).toContain('model ConversationCitation');
    expect(engagement).toContain('model ToolProposalRecord');
    expect(engagement).toContain('model SupportHandoff');
    expect(operations).toContain('model ReleaseDecisionEvent');
  });

  it('requires governed source metadata for externally sourced projections', () => {
    const platform = readFileSync(join(modelRoot, 'platform.prisma'), 'utf8');

    expect(platform).toContain('ownerRef');
    expect(platform).toContain('provenanceUri');
    expect(platform).toContain('licenseId');
    expect(platform).toContain('classification');
    expect(platform).toContain('freshnessTtlSeconds');
    expect(platform).toContain('approvalState');
  });
});
