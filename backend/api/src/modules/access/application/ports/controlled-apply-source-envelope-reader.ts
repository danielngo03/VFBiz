/**
 * API-owned read boundary for a signed authority envelope.
 *
 * Implementations must address one exact GCS generation and verify the
 * provider's generation, size and CRC32C metadata before yielding bytes. The
 * caller deliberately receives no precomputed SHA-256: the API hashes the
 * streamed bytes itself so a detached digest cannot self-attest authority.
 */
export interface ControlledApplySourceEnvelopeReadRequest {
  readonly sourceEnvelopeUri: string;
  readonly generation: bigint;
}

export interface ControlledApplySourceEnvelopeBytes {
  readonly generation: bigint;
  readonly sizeBytes: bigint;
  readonly crc32cBase64: string;
  readonly bytes: AsyncIterable<Uint8Array>;
}

export abstract class ControlledApplySourceEnvelopeReader {
  abstract readExact(
    request: ControlledApplySourceEnvelopeReadRequest,
  ): Promise<ControlledApplySourceEnvelopeBytes>;
}
