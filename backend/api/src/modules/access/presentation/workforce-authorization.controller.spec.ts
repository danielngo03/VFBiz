import { idempotencyRequestHash } from './workforce-authorization.controller';

describe('idempotencyRequestHash', () => {
  it('is deterministic for the same principal and body', () => {
    const body = { name: 'Support tier 1', description: 'Read-only support' };

    expect(idempotencyRequestHash('worker-1', body)).toBe(
      idempotencyRequestHash('worker-1', body),
    );
  });

  it('scopes the hash by principal so two subjects reusing the same key and body do not collide', () => {
    const body = { name: 'Support tier 1', description: 'Read-only support' };

    const workerOneHash = idempotencyRequestHash('worker-1', body);
    const workerTwoHash = idempotencyRequestHash('worker-2', body);

    expect(workerOneHash).not.toBe(workerTwoHash);
  });

  it('changes the hash when the body differs for the same principal', () => {
    const first = idempotencyRequestHash('worker-1', { name: 'Role A' });
    const second = idempotencyRequestHash('worker-1', { name: 'Role B' });

    expect(first).not.toBe(second);
  });

  it('is independent of object key order (canonical JSON)', () => {
    const first = idempotencyRequestHash('worker-1', { a: 1, b: 2 });
    const second = idempotencyRequestHash('worker-1', { b: 2, a: 1 });

    expect(first).toBe(second);
  });
});
