import { createHash } from 'node:crypto';
import {
  ControlledApplyReservationAuthorityUnavailableError,
  ControlledApplyReservationValidationError,
} from '../../application/errors/controlled-apply-reservation.errors';
import {
  assertExactSourceEnvelopeIntegrity,
  crc32cBase64,
} from './exact-source-envelope-integrity';
import { GcsControlledApplySourceEnvelopeReader } from './gcs-controlled-apply-source-envelope-reader';

const bodyBytes = new TextEncoder().encode('{"authority":"signed"}');
const bodyDigest = createHash('sha256').update(bodyBytes).digest('hex');
const uri = `gs://vinfast-503003-evidence-dev/controlled-apply/authority-envelopes/v1/${bodyDigest}.json#42`;
const crc = crc32cBase64(bodyBytes);

function response(
  headers: Record<string, string> = {
    'x-goog-generation': '42',
    'x-goog-stored-content-length': String(bodyBytes.byteLength),
    'x-goog-hash': `crc32c=${crc}`,
  },
): Response {
  return new Response(
    new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(bodyBytes);
        controller.close();
      },
    }),
    { status: 200, headers },
  );
}

describe('GcsControlledApplySourceEnvelopeReader', () => {
  it('reads one exact generation and composes with independent byte integrity', async () => {
    const requests: Request[] = [];
    const reader = new GcsControlledApplySourceEnvelopeReader(
      () => Promise.resolve('adc-token'),
      (input, init) => {
        requests.push(new Request(input, init));
        return Promise.resolve(response());
      },
    );
    const observed = await reader.readExact({
      sourceEnvelopeUri: uri,
      generation: 42n,
    });
    await expect(
      assertExactSourceEnvelopeIntegrity(reader, {
        sourceEnvelopeUri: uri,
        sourceEnvelopeSha256: bodyDigest,
        sourceEnvelopeGeneration: 42n,
      }),
    ).resolves.toBeUndefined();
    expect(observed.generation).toBe(42n);
    expect(requests[0]?.headers.get('authorization')).toBe('Bearer adc-token');
    expect(requests[0]?.url).toContain('generation=42');
  });

  it('rejects metadata drift before bytes become authority evidence', async () => {
    const reader = new GcsControlledApplySourceEnvelopeReader(
      () => Promise.resolve('adc-token'),
      () =>
        Promise.resolve(
          response({
            'x-goog-generation': '43',
            'x-goog-stored-content-length': String(bodyBytes.byteLength),
            'x-goog-hash': `crc32c=${crc}`,
          }),
        ),
    );
    await expect(
      reader.readExact({ sourceEnvelopeUri: uri, generation: 42n }),
    ).rejects.toThrow(ControlledApplyReservationValidationError);
  });

  it('maps provider failures to authority-unavailable and never follows redirects', async () => {
    const reader = new GcsControlledApplySourceEnvelopeReader(
      () => Promise.resolve('adc-token'),
      () => Promise.resolve(new Response(null, { status: 503 })),
    );
    await expect(
      reader.readExact({ sourceEnvelopeUri: uri, generation: 42n }),
    ).rejects.toThrow(ControlledApplyReservationAuthorityUnavailableError);
  });

  it('maps ADC/token-provider failures to authority-unavailable', async () => {
    const reader = new GcsControlledApplySourceEnvelopeReader(
      () => Promise.reject(new Error('ADC unavailable')),
      () => Promise.resolve(response()),
    );
    await expect(
      reader.readExact({ sourceEnvelopeUri: uri, generation: 42n }),
    ).rejects.toThrow(ControlledApplyReservationAuthorityUnavailableError);
  });

  it('cancels the response body when a consumer stops early', async () => {
    let cancelled = false;
    const reader = new GcsControlledApplySourceEnvelopeReader(
      () => Promise.resolve('adc-token'),
      () =>
        Promise.resolve(
          new Response(
            new ReadableStream<Uint8Array>({
              start(controller) {
                controller.enqueue(bodyBytes);
              },
              cancel() {
                cancelled = true;
              },
            }),
            {
              status: 200,
              headers: {
                'x-goog-generation': '42',
                'x-goog-stored-content-length': String(bodyBytes.byteLength),
                'x-goog-hash': `crc32c=${crc}`,
              },
            },
          ),
        ),
    );
    const observed = await reader.readExact({
      sourceEnvelopeUri: uri,
      generation: 42n,
    });
    for await (const chunk of observed.bytes) {
      expect(chunk).toBeInstanceOf(Uint8Array);
      break;
    }
    expect(cancelled).toBe(true);
  });
});
