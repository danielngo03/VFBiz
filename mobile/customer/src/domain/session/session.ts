export type AuthStatus =
  | "restoring"
  | "anonymous"
  | "authenticating"
  | "authenticated"
  | "refreshing"
  | "signing-out"
  | "error";

export interface CustomerCredential {
  accessToken: string;
  refreshToken?: string;
  idToken?: string;
  tokenType: string;
  expiresAt: number;
  subject: string;
  issuer: string;
  clientId: string;
  environment: string;
  market: string;
}

export interface AuthState {
  status: AuthStatus;
  credential: CustomerCredential | null;
  error: string | null;
}

export type AuthEvent =
  | { type: "RESTORED"; credential: CustomerCredential | null }
  | { type: "SIGN_IN_STARTED" }
  | { type: "AUTHENTICATED"; credential: CustomerCredential }
  | { type: "REFRESH_STARTED" }
  | { type: "SIGN_OUT_STARTED" }
  | { type: "SIGNED_OUT" }
  | { type: "FAILED"; message: string };

export const initialAuthState: AuthState = {
  status: "restoring",
  credential: null,
  error: null,
};

export function authReducer(state: AuthState, event: AuthEvent): AuthState {
  switch (event.type) {
    case "RESTORED":
      return {
        status: event.credential ? "authenticated" : "anonymous",
        credential: event.credential,
        error: null,
      };
    case "SIGN_IN_STARTED":
      return { ...state, status: "authenticating", error: null };
    case "AUTHENTICATED":
      return { status: "authenticated", credential: event.credential, error: null };
    case "REFRESH_STARTED":
      return { ...state, status: "refreshing", error: null };
    case "SIGN_OUT_STARTED":
      return { ...state, status: "signing-out", error: null };
    case "SIGNED_OUT":
      return { status: "anonymous", credential: null, error: null };
    case "FAILED":
      return { ...state, status: "error", error: event.message };
  }
}
