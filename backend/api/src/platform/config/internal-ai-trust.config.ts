import { isAbsolute, normalize } from 'node:path';
import { Injectable } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import type { EnvironmentVariables } from './env.schema';

export type InternalAiAssertionAlgorithm = 'ES256' | 'EdDSA';

export interface InternalAiSigningKeyReference {
  readonly algorithm: InternalAiAssertionAlgorithm;
  readonly kid: string;
  readonly privateKeyFile: string;
}

export interface InternalAiTrustSettings {
  readonly activeKeyId: string | null;
  readonly allowedHosts: ReadonlySet<string>;
  readonly assertionAudience: 'vfbiz-ai';
  readonly assertionIssuer: 'vfbiz-api';
  readonly assertionTtlSeconds: number;
  readonly baseUrl: string | null;
  readonly enabled: boolean;
  readonly dispatchEnabled: boolean;
  readonly keyReferences: readonly InternalAiSigningKeyReference[];
  readonly requestTimeoutMs: number;
  readonly retryBudget: number;
  readonly subjectPseudonymizationKey: string | null;
}

const KEY_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$/;
const MAX_KEY_REFERENCES = 3;

@Injectable()
export class InternalAiTrustConfig implements InternalAiTrustSettings {
  readonly activeKeyId: string | null;
  readonly allowedHosts: ReadonlySet<string>;
  readonly assertionAudience: 'vfbiz-ai';
  readonly assertionIssuer: 'vfbiz-api';
  readonly assertionTtlSeconds: number;
  readonly baseUrl: string | null;
  readonly enabled: boolean;
  readonly dispatchEnabled: boolean;
  readonly keyReferences: readonly InternalAiSigningKeyReference[];
  readonly requestTimeoutMs: number;
  readonly retryBudget: number;
  readonly subjectPseudonymizationKey: string | null;

  constructor(config: ConfigService<EnvironmentVariables, true>) {
    this.enabled = config.get('VFBIZ_INTERNAL_AI_ENABLED', { infer: true });
    this.dispatchEnabled = config.get('VFBIZ_INTERNAL_AI_DISPATCH_ENABLED', {
      infer: true,
    });
    this.requestTimeoutMs = config.get('VFBIZ_INTERNAL_AI_REQUEST_TIMEOUT_MS', {
      infer: true,
    });
    this.retryBudget = config.get('VFBIZ_INTERNAL_AI_RETRY_BUDGET', {
      infer: true,
    });
    this.assertionIssuer = config.get('VFBIZ_INTERNAL_AI_ASSERTION_ISSUER', {
      infer: true,
    });
    this.assertionAudience = config.get(
      'VFBIZ_INTERNAL_AI_ASSERTION_AUDIENCE',
      { infer: true },
    );
    this.assertionTtlSeconds = config.get(
      'VFBIZ_INTERNAL_AI_ASSERTION_TTL_SECONDS',
      { infer: true },
    );
    if (!this.enabled) {
      this.activeKeyId = null;
      this.allowedHosts = new Set();
      this.baseUrl = null;
      this.keyReferences = Object.freeze([]);
      this.subjectPseudonymizationKey = null;
      Object.freeze(this);
      return;
    }

    this.baseUrl = config.getOrThrow('VFBIZ_INTERNAL_AI_BASE_URL', {
      infer: true,
    });
    this.allowedHosts = parseAllowedHosts(
      config.getOrThrow('VFBIZ_INTERNAL_AI_ALLOWED_HOSTS', { infer: true }),
    );
    this.activeKeyId = config.getOrThrow(
      'VFBIZ_INTERNAL_AI_ASSERTION_ACTIVE_KEY_ID',
      { infer: true },
    );
    this.keyReferences = parseKeyring(
      config.getOrThrow('VFBIZ_INTERNAL_AI_ASSERTION_KEYRING', {
        infer: true,
      }),
    );
    this.subjectPseudonymizationKey = config.getOrThrow(
      'VFBIZ_INTERNAL_AI_SUBJECT_PSEUDONYMIZATION_KEY',
      { infer: true },
    );

    if (!this.keyReferences.some(({ kid }) => kid === this.activeKeyId)) {
      throw new Error(
        'Internal AI assertion active key id is absent from the keyring',
      );
    }
    Object.freeze(this);
  }
}

function parseAllowedHosts(value: string): ReadonlySet<string> {
  return new Set(
    value.split(',').map((host) =>
      host
        .trim()
        .replace(/^\[|\]$/g, '')
        .toLowerCase(),
    ),
  );
}

function parseKeyring(value: string): readonly InternalAiSigningKeyReference[] {
  let parsed: unknown;
  try {
    parsed = JSON.parse(value);
  } catch {
    throw new Error('Internal AI assertion keyring must be valid JSON');
  }
  if (!isExactRecord(parsed, ['keys']) || !Array.isArray(parsed.keys)) {
    throw new Error(
      'Internal AI assertion keyring must contain only a keys array',
    );
  }
  if (parsed.keys.length === 0 || parsed.keys.length > MAX_KEY_REFERENCES) {
    throw new Error(
      `Internal AI assertion keyring must contain between 1 and ${MAX_KEY_REFERENCES} keys`,
    );
  }

  const ids = new Set<string>();
  const files = new Set<string>();
  const references = parsed.keys.map(
    (candidate: unknown): InternalAiSigningKeyReference => {
      if (
        !isExactRecord(candidate, ['alg', 'kid', 'privateKeyFile']) ||
        (candidate.alg !== 'ES256' && candidate.alg !== 'EdDSA') ||
        typeof candidate.kid !== 'string' ||
        !KEY_ID_PATTERN.test(candidate.kid) ||
        typeof candidate.privateKeyFile !== 'string' ||
        !isAbsolute(candidate.privateKeyFile)
      ) {
        throw new Error(
          'Internal AI assertion key entries require alg, valid kid and absolute privateKeyFile',
        );
      }
      const privateKeyFile = normalize(candidate.privateKeyFile);
      if (ids.has(candidate.kid)) {
        throw new Error('Internal AI assertion key ids must be unique');
      }
      if (files.has(privateKeyFile)) {
        throw new Error(
          'Internal AI assertion keys must use distinct private key files',
        );
      }
      ids.add(candidate.kid);
      files.add(privateKeyFile);
      return Object.freeze({
        algorithm: candidate.alg,
        kid: candidate.kid,
        privateKeyFile,
      });
    },
  );
  return Object.freeze(references);
}

function isExactRecord(
  value: unknown,
  keys: readonly string[],
): value is Record<string, unknown> {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    return false;
  }
  const actualKeys = Object.keys(value).sort();
  const expectedKeys = [...keys].sort();
  return (
    actualKeys.length === expectedKeys.length &&
    actualKeys.every((key, index) => key === expectedKeys[index])
  );
}
