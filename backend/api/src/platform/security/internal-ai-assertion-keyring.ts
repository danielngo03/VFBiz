import {
  createPrivateKey,
  createPublicKey,
  type JsonWebKey,
  type KeyObject,
} from 'node:crypto';
import {
  closeSync,
  constants,
  fstatSync,
  openSync,
  readFileSync,
} from 'node:fs';
import { Injectable } from '@nestjs/common';
import {
  InternalAiTrustConfig,
  type InternalAiAssertionAlgorithm,
} from '../config/internal-ai-trust.config';

const MAX_PRIVATE_KEY_BYTES = 16_384;
export interface InternalAiPublicJwk extends JsonWebKey {
  readonly alg: InternalAiAssertionAlgorithm;
  readonly kid: string;
  readonly key_ops: readonly ['verify'];
  readonly use: 'sig';
}

export interface InternalAiSigningKey {
  readonly algorithm: InternalAiAssertionAlgorithm;
  readonly kid: string;
  readonly privateKey: KeyObject;
  readonly publicJwk: InternalAiPublicJwk;
}

@Injectable()
export class InternalAiAssertionKeyring {
  private readonly active: InternalAiSigningKey | null;
  private readonly keys: ReadonlyMap<string, InternalAiSigningKey>;
  private readonly publicKeys: readonly InternalAiPublicJwk[];

  constructor(config: InternalAiTrustConfig) {
    if (!config.enabled) {
      this.active = null;
      this.keys = new Map();
      this.publicKeys = Object.freeze([]);
      return;
    }
    const loaded = config.keyReferences.map((reference) =>
      loadSigningKey(
        reference.kid,
        reference.algorithm,
        reference.privateKeyFile,
      ),
    );
    this.keys = new Map(loaded.map((key) => [key.kid, key]));
    const activeKeyId = config.activeKeyId;
    if (activeKeyId === null) {
      throw new Error(
        'Enabled internal AI trust config requires an active key id',
      );
    }
    const active = this.keys.get(activeKeyId);
    if (active === undefined) {
      throw new Error(
        'Internal AI assertion active signing key is unavailable',
      );
    }
    this.active = active;
    this.publicKeys = Object.freeze(loaded.map(({ publicJwk }) => publicJwk));
  }

  activeSigningKey(): InternalAiSigningKey {
    if (this.active === null) {
      throw new Error('Internal AI assertion signing is disabled');
    }
    return this.active;
  }

  publicJwks(): Readonly<{ keys: readonly InternalAiPublicJwk[] }> {
    return Object.freeze({
      keys: Object.freeze(
        this.publicKeys.map((key) =>
          Object.freeze({ ...key }),
        ) as InternalAiPublicJwk[],
      ),
    });
  }
}

function loadSigningKey(
  kid: string,
  algorithm: InternalAiAssertionAlgorithm,
  privateKeyFile: string,
): InternalAiSigningKey {
  const descriptor = openSync(privateKeyFile, constants.O_RDONLY);
  let keyBytes: Buffer;
  try {
    const stat = fstatSync(descriptor);
    if (
      !stat.isFile() ||
      stat.size === 0 ||
      stat.size > MAX_PRIVATE_KEY_BYTES
    ) {
      throw new Error(
        `Internal AI assertion key ${kid} must reference a non-empty bounded regular file`,
      );
    }
    if ((stat.mode & 0o077) !== 0) {
      throw new Error(
        `Internal AI assertion key ${kid} file must be readable only by its owner`,
      );
    }
    if (
      typeof process.getuid === 'function' &&
      process.getuid() !== 0 &&
      stat.uid !== process.getuid()
    ) {
      throw new Error(
        `Internal AI assertion key ${kid} file must be owned by the API process user`,
      );
    }
    keyBytes = readFileSync(descriptor);
  } finally {
    closeSync(descriptor);
  }
  let privateKey: KeyObject;
  try {
    privateKey = createPrivateKey(keyBytes);
  } finally {
    keyBytes.fill(0);
  }
  assertAlgorithmMatchesKey(kid, algorithm, privateKey);
  const publicKey = createPublicKey(privateKey);
  const exported = publicKey.export({ format: 'jwk' });
  const publicJwk = Object.freeze({
    ...exported,
    alg: algorithm,
    kid,
    key_ops: Object.freeze(['verify'] as const),
    use: 'sig' as const,
  });
  assertPublicOnly(kid, publicJwk);
  return Object.freeze({ algorithm, kid, privateKey, publicJwk });
}

function assertAlgorithmMatchesKey(
  kid: string,
  algorithm: InternalAiAssertionAlgorithm,
  privateKey: KeyObject,
): void {
  if (algorithm === 'ES256') {
    if (
      privateKey.asymmetricKeyType !== 'ec' ||
      privateKey.asymmetricKeyDetails?.namedCurve !== 'prime256v1'
    ) {
      throw new Error(
        `Internal AI assertion key ${kid} must be a P-256 EC private key for ES256`,
      );
    }
    return;
  }
  if (privateKey.asymmetricKeyType !== 'ed25519') {
    throw new Error(
      `Internal AI assertion key ${kid} must be an Ed25519 private key for EdDSA`,
    );
  }
}

function assertPublicOnly(kid: string, jwk: JsonWebKey): void {
  const privateMembers = ['d', 'p', 'q', 'dp', 'dq', 'qi', 'oth', 'k'];
  if (privateMembers.some((member) => member in jwk)) {
    throw new Error(
      `Internal AI assertion public JWK ${kid} contains private key material`,
    );
  }
}
