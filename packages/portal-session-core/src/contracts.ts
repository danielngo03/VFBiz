import "server-only";
import type Redis from "ioredis";

export type OpaquePortalSessionId = string & {
  readonly __opaquePortalSessionId: unique symbol;
};

export interface VaultKeyring {
  readonly activeKeyId: string;
  key(keyId: string): Buffer | undefined;
}

export interface PortalSessionMetadata {
  readonly authenticatedAt: Date;
  readonly expiresAt: Date;
  readonly id: OpaquePortalSessionId;
  readonly lastSeenAt: Date;
  readonly providerSessionId: string;
  readonly subject: string;
}

export interface PortalSessionRecord<TPayload> {
  readonly metadata: PortalSessionMetadata;
  readonly payload: TPayload;
  readonly revision: string;
}

export interface StoredPortalSession<TPayload> {
  readonly metadata: {
    readonly authenticatedAt: string;
    readonly expiresAt: string;
    readonly id: string;
    readonly lastSeenAt: string;
    readonly providerSessionId: string;
    readonly subject: string;
  };
  readonly payload: TPayload;
}

export interface PortalSessionRepositoryOptions<TPayload> {
  readonly activityPrefix?: string;
  readonly idleTimeoutSeconds: number;
  readonly keyring: VaultKeyring;
  readonly maxAgeSeconds: number;
  readonly namespace: string;
  readonly redis: Redis;
  readonly validatePayload?: (value: unknown) => TPayload;
}

export interface SessionWriteOptions {
  readonly expectedRevision?: string;
}

export type BackchannelReplayClaim =
  | { readonly state: "acquired"; readonly token: string }
  | { readonly state: "completed" }
  | { readonly state: "in_progress" };

export interface ClientContext {
  readonly deviceLabel: string | null;
  readonly networkHint: string | null;
  readonly userAgentSummary: string | null;
}
