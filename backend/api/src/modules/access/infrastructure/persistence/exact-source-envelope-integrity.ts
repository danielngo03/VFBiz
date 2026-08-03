import { createHash } from 'node:crypto';
import {
  ControlledApplyReservationConflictError,
  ControlledApplyReservationValidationError,
} from '../../application/errors/controlled-apply-reservation.errors';
import type { ControlledApplySourceEnvelopeReader } from '../../application/ports/controlled-apply-source-envelope-reader';
import type { VerifiedControlledApplyRequest } from '../../domain/controlled-apply-reservation';

const MAX_SOURCE_ENVELOPE_BYTES = 64 * 1024;
const CRC32C_BASE64 = /^[A-Za-z0-9+/]{6}==$/;
const SOURCE_ENVELOPE_URI =
  /^gs:\/\/vinfast-503003-evidence-dev\/controlled-apply\/authority-envelopes\/v1\/([a-f0-9]{64})\.json#([1-9][0-9]*)$/;

const CRC32C_TABLE = (() => {
  const table = new Uint32Array(256);
  for (let index = 0; index < table.length; index += 1) {
    let value = index;
    for (let bit = 0; bit < 8; bit += 1) {
      value = (value & 1) === 0 ? value >>> 1 : (value >>> 1) ^ 0x82f63b78;
    }
    table[index] = value >>> 0;
  }
  return table;
})();

export function crc32cBase64(bytes: Uint8Array): string {
  let value = 0xffffffff;
  for (const byte of bytes) {
    value = CRC32C_TABLE[(value ^ byte) & 0xff] ^ (value >>> 8);
  }
  const final = (value ^ 0xffffffff) >>> 0;
  const encoded = Buffer.allocUnsafe(4);
  encoded.writeUInt32BE(final, 0);
  return encoded.toString('base64');
}

/**
 * Revalidate the exact source envelope before any authority join is accepted.
 * The reader is generation-pinned and provider-integrity checked; this
 * function independently streams and hashes the bytes that the API observed.
 */
export async function assertExactSourceEnvelopeIntegrity(
  reader: ControlledApplySourceEnvelopeReader,
  input: Pick<
    VerifiedControlledApplyRequest,
    'sourceEnvelopeUri' | 'sourceEnvelopeSha256' | 'sourceEnvelopeGeneration'
  >,
): Promise<void> {
  const locator = SOURCE_ENVELOPE_URI.exec(input.sourceEnvelopeUri);
  if (
    locator === null ||
    locator[1] !== input.sourceEnvelopeSha256 ||
    input.sourceEnvelopeGeneration <= 0n ||
    BigInt(locator[2]) !== input.sourceEnvelopeGeneration
  ) {
    throw new ControlledApplyReservationValidationError(
      'source envelope URI does not bind a positive exact generation and digest',
    );
  }
  const observed = await reader.readExact({
    sourceEnvelopeUri: input.sourceEnvelopeUri,
    generation: input.sourceEnvelopeGeneration,
  });
  if (
    typeof observed.generation !== 'bigint' ||
    typeof observed.sizeBytes !== 'bigint' ||
    typeof observed.crc32cBase64 !== 'string' ||
    !CRC32C_BASE64.test(observed.crc32cBase64) ||
    observed.generation !== input.sourceEnvelopeGeneration
  ) {
    throw new ControlledApplyReservationConflictError(
      'source envelope generation or integrity metadata changed during verification',
    );
  }
  if (
    observed.sizeBytes < 0n ||
    observed.sizeBytes > BigInt(MAX_SOURCE_ENVELOPE_BYTES) ||
    !observed.crc32cBase64.trim()
  ) {
    throw new ControlledApplyReservationValidationError(
      'source envelope integrity metadata is invalid',
    );
  }

  const digest = createHash('sha256');
  let crc32c = 0xffffffff;
  let observedBytes = 0n;
  for await (const chunk of observed.bytes) {
    if (!(chunk instanceof Uint8Array) || chunk.byteLength === 0) {
      throw new ControlledApplyReservationValidationError(
        'source envelope stream yielded invalid bytes',
      );
    }
    observedBytes += BigInt(chunk.byteLength);
    if (observedBytes > BigInt(MAX_SOURCE_ENVELOPE_BYTES)) {
      throw new ControlledApplyReservationValidationError(
        'source envelope exceeds the 64 KiB authority cap',
      );
    }
    digest.update(chunk);
    for (const byte of chunk) {
      crc32c = CRC32C_TABLE[(crc32c ^ byte) & 0xff] ^ (crc32c >>> 8);
    }
  }
  if (observedBytes !== observed.sizeBytes) {
    throw new ControlledApplyReservationConflictError(
      'source envelope size changed during verification',
    );
  }
  if (digest.digest('hex') !== input.sourceEnvelopeSha256) {
    throw new ControlledApplyReservationConflictError(
      'source envelope bytes do not match the signed digest',
    );
  }
  const crcBytes = Buffer.allocUnsafe(4);
  crcBytes.writeUInt32BE((crc32c ^ 0xffffffff) >>> 0, 0);
  if (crcBytes.toString('base64') !== observed.crc32cBase64) {
    throw new ControlledApplyReservationConflictError(
      'source envelope bytes do not match the provider CRC32C',
    );
  }
}
