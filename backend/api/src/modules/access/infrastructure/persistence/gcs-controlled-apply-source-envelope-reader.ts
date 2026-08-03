import {
  ControlledApplyReservationAuthorityUnavailableError,
  ControlledApplyReservationValidationError,
} from '../../application/errors/controlled-apply-reservation.errors';
import {
  ControlledApplySourceEnvelopeReader,
  type ControlledApplySourceEnvelopeBytes,
  type ControlledApplySourceEnvelopeReadRequest,
} from '../../application/ports/controlled-apply-source-envelope-reader';

const SOURCE_URI =
  /^gs:\/\/vinfast-503003-evidence-dev\/controlled-apply\/authority-envelopes\/v1\/([a-f0-9]{64})\.json#([1-9][0-9]*)$/;
const GENERATION = /^[1-9][0-9]*$/;
const CRC32C = /^[A-Za-z0-9+/]{6}==$/;
const MAX_TOKEN_BYTES = 8192;
const REQUEST_TIMEOUT_MS = 5_000;

export type AccessTokenProvider = () => Promise<string>;
export type FetchImplementation = typeof fetch;

/**
 * Generation-pinned GCS reader for the private authority-envelope bucket.
 * It returns provider integrity metadata but never a provider-computed
 * SHA-256; the API-level integrity utility hashes the streamed body.
 */
export class GcsControlledApplySourceEnvelopeReader extends ControlledApplySourceEnvelopeReader {
  constructor(
    private readonly accessTokenProvider: AccessTokenProvider,
    private readonly fetchImplementation: FetchImplementation = fetch,
  ) {
    super();
  }

  async readExact(
    request: ControlledApplySourceEnvelopeReadRequest,
  ): Promise<ControlledApplySourceEnvelopeBytes> {
    const locator = SOURCE_URI.exec(request.sourceEnvelopeUri);
    if (
      locator === null ||
      !GENERATION.test(locator[2]) ||
      BigInt(locator[2]) !== request.generation
    ) {
      throw new ControlledApplyReservationValidationError(
        'source envelope URI is not an exact generation-pinned authority object',
      );
    }

    let token: string;
    try {
      token = await this.accessTokenProvider();
    } catch (error) {
      void error;
      throw new ControlledApplyReservationAuthorityUnavailableError(
        'GCS access token could not be obtained',
      );
    }
    if (
      typeof token !== 'string' ||
      token.length === 0 ||
      token.length > MAX_TOKEN_BYTES ||
      /\s/.test(token)
    ) {
      throw new ControlledApplyReservationValidationError(
        'GCS access token is invalid',
      );
    }

    const objectName = `controlled-apply/authority-envelopes/v1/${locator[1]}.json`;
    const url = new URL(
      `https://storage.googleapis.com/storage/v1/b/vinfast-503003-evidence-dev/o/${encodeURIComponent(objectName)}`,
    );
    url.searchParams.set('generation', locator[2]);
    url.searchParams.set('alt', 'media');

    let response: Response;
    try {
      response = await this.fetchImplementation(url, {
        method: 'GET',
        headers: {
          authorization: `Bearer ${token}`,
          accept: 'application/json',
        },
        redirect: 'error',
        signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
      });
    } catch (error) {
      void error;
      throw new ControlledApplyReservationAuthorityUnavailableError(
        'exact GCS authority object could not be read',
      );
    }
    if (!response.ok) {
      throw new ControlledApplyReservationAuthorityUnavailableError(
        `exact GCS authority object returned HTTP ${response.status}`,
      );
    }
    if (response.body === null) {
      throw new ControlledApplyReservationValidationError(
        'exact GCS authority object has no body',
      );
    }

    const observedGeneration = response.headers.get('x-goog-generation');
    const sizeHeader =
      response.headers.get('x-goog-stored-content-length') ??
      response.headers.get('content-length');
    const crc32cBase64 = parseCrc32c(response.headers.get('x-goog-hash'));
    if (
      observedGeneration !== locator[2] ||
      sizeHeader === null ||
      !/^\d+$/.test(sizeHeader) ||
      crc32cBase64 === null
    ) {
      throw new ControlledApplyReservationValidationError(
        'GCS response is missing exact generation, size or CRC32C metadata',
      );
    }
    return {
      generation: BigInt(observedGeneration),
      sizeBytes: BigInt(sizeHeader),
      crc32cBase64,
      bytes: bodyBytes(response.body),
    };
  }
}

function parseCrc32c(header: string | null): string | null {
  if (header === null) return null;
  const value = header
    .split(',')
    .map((part) => part.trim())
    .find((part) => part.startsWith('crc32c='))
    ?.slice('crc32c='.length);
  return value !== undefined && CRC32C.test(value) ? value : null;
}

async function* bodyBytes(
  body: ReadableStream<Uint8Array>,
): AsyncIterable<Uint8Array> {
  const reader = body.getReader();
  let completed = false;
  try {
    while (true) {
      const next = await reader.read();
      if (next.done) {
        completed = true;
        return;
      }
      yield next.value;
    }
  } finally {
    if (!completed) {
      try {
        await reader.cancel();
      } catch (error) {
        void error;
      }
    }
    reader.releaseLock();
  }
}
