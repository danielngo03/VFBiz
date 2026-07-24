export interface PrivacyActionState {
  readonly correlationId?: string;
  readonly message?: string;
  readonly ok: boolean;
}

export const initialConsentActionState: PrivacyActionState = { ok: false };
export const initialDataRequestActionState: PrivacyActionState = { ok: false };
