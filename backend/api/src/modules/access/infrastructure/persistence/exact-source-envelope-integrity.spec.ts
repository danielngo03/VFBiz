import { createHash } from 'node:crypto';
import {
  ControlledApplyReservationConflictError,
  ControlledApplyReservationValidationError,
} from '../../application/errors/controlled-apply-reservation.errors';
import type {
  ControlledApplySourceEnvelopeBytes,
  ControlledApplySourceEnvelopeReadRequest,
} from '../../application/ports/controlled-apply-source-envelope-reader';
import { ControlledApplySourceEnvelopeReader } from '../../application/ports/controlled-apply-source-envelope-reader';
import {
  assertExactSourceEnvelopeIntegrity,
  crc32cBase64,
} from './exact-source-envelope-integrity';

const bytes = new TextEncoder().encode('{"authority":"signed"}');
const digest = createHash('sha256').update(bytes).digest('hex');
const sourceEnvelopeUri =
  'gs://vinfast-503003-evidence-dev/controlled-apply/authority-envelopes/v1/' +
  `${digest}.json#42`;

class FakeReader extends ControlledApplySourceEnvelopeReader {
  constructor(private readonly response: ControlledApplySourceEnvelopeBytes) {
    super();
  }

  readExact(
    request: ControlledApplySourceEnvelopeReadRequest,
  ): Promise<ControlledApplySourceEnvelopeBytes> {
    void request;
    return Promise.resolve(this.response);
  }
}

function response(
  overrides: Partial<ControlledApplySourceEnvelopeBytes> = {},
): ControlledApplySourceEnvelopeBytes {
  return {
    generation: 42n,
    sizeBytes: BigInt(bytes.byteLength),
    crc32cBase64: crc32cBase64(bytes),
    bytes: (async function* () {
      await Promise.resolve();
      yield bytes;
    })(),
    ...overrides,
  };
}

describe('assertExactSourceEnvelopeIntegrity', () => {
  it('rehashes generation-pinned bytes and accepts matching metadata', async () => {
    await expect(
      assertExactSourceEnvelopeIntegrity(new FakeReader(response()), {
        sourceEnvelopeUri,
        sourceEnvelopeSha256: digest,
        sourceEnvelopeGeneration: 42n,
      }),
    ).resolves.toBeUndefined();
  });

  it('rejects generation drift and byte mutation', async () => {
    await expect(
      assertExactSourceEnvelopeIntegrity(
        new FakeReader(response({ generation: 43n })),
        {
          sourceEnvelopeUri,
          sourceEnvelopeSha256: digest,
          sourceEnvelopeGeneration: 42n,
        },
      ),
    ).rejects.toThrow(ControlledApplyReservationConflictError);

    const mutated = new TextEncoder().encode('{"authority":"mutated"}');
    await expect(
      assertExactSourceEnvelopeIntegrity(
        new FakeReader(
          response({
            sizeBytes: BigInt(mutated.byteLength),
            bytes: (async function* () {
              await Promise.resolve();
              yield mutated;
            })(),
          }),
        ),
        {
          sourceEnvelopeUri,
          sourceEnvelopeSha256: digest,
          sourceEnvelopeGeneration: 42n,
        },
      ),
    ).rejects.toThrow(ControlledApplyReservationConflictError);
  });

  it('rejects a stream that exceeds the authority payload cap', async () => {
    const oversized = new Uint8Array(64 * 1024 + 1);
    await expect(
      assertExactSourceEnvelopeIntegrity(
        new FakeReader(
          response({
            sizeBytes: BigInt(oversized.byteLength),
            bytes: (async function* () {
              await Promise.resolve();
              yield oversized;
            })(),
          }),
        ),
        {
          sourceEnvelopeUri,
          sourceEnvelopeSha256: digest,
          sourceEnvelopeGeneration: 42n,
        },
      ),
    ).rejects.toThrow(ControlledApplyReservationValidationError);
  });

  it('rejects provider CRC32C metadata that does not match the bytes', async () => {
    await expect(
      assertExactSourceEnvelopeIntegrity(
        new FakeReader(response({ crc32cBase64: 'AAAAAA==' })),
        {
          sourceEnvelopeUri,
          sourceEnvelopeSha256: digest,
          sourceEnvelopeGeneration: 42n,
        },
      ),
    ).rejects.toThrow(ControlledApplyReservationConflictError);
  });
});
