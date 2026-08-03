import * as AuthSession from "expo-auth-session";
import * as WebBrowser from "expo-web-browser";
import * as Crypto from "expo-crypto";
import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useReducer,
} from "react";
import type { QueryClient } from "@tanstack/react-query";
import {
  authReducer,
  initialAuthState,
  type AuthState,
  type CustomerCredential,
} from "../../domain/session/session";
import { runtimeConfig } from "../config/runtime-config";
import { recordHandledError } from "../observability/logger";
import { cacheNamespace } from "../storage/cache-namespace";
import { wipeSubjectPartition } from "../storage/database";
import { clearCustomerTemporaryFiles } from "../storage/temporary-files";
import {
  clearCredential,
  loadCredential,
  saveCredential,
} from "./credential-store";
import { validateIdentityToken } from "./jwt-subject";
import { performLocalLogout } from "./logout";
import {
  clearCleanupMarker,
  loadCleanupMarker,
  markCleanupPending,
} from "./cleanup-marker";

WebBrowser.maybeCompleteAuthSession();

interface AuthContextValue extends AuthState {
  signIn(): Promise<void>;
  refresh(): Promise<void>;
  signOut(): Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function credentialFromToken(
  token: AuthSession.TokenResponse,
  previous?: CustomerCredential,
  expectedNonce?: string,
): CustomerCredential {
  const idToken = token.idToken ?? previous?.idToken;
  const refreshToken = token.refreshToken ?? previous?.refreshToken;
  const subject = token.idToken
    ? validateIdentityToken(token.idToken, {
        issuer: runtimeConfig.oidcIssuer,
        clientId: runtimeConfig.oidcClientId,
        ...(expectedNonce ? { nonce: expectedNonce } : {}),
      })
    : previous?.subject;
  if (!subject) throw new Error("A verified customer subject is required.");
  if (previous && subject !== previous.subject)
    throw new Error("Refreshed identity changed customer subject.");
  return {
    accessToken: token.accessToken,
    ...(refreshToken ? { refreshToken } : {}),
    ...(idToken ? { idToken } : {}),
    tokenType: token.tokenType ?? "Bearer",
    expiresAt: (token.issuedAt + (token.expiresIn ?? 300)) * 1000,
    subject,
    issuer: runtimeConfig.oidcIssuer,
    clientId: runtimeConfig.oidcClientId,
    environment: runtimeConfig.environment,
    market: runtimeConfig.market,
  };
}

function credentialMatchesRuntime(credential: CustomerCredential): boolean {
  return (
    credential.issuer === runtimeConfig.oidcIssuer &&
    credential.clientId === runtimeConfig.oidcClientId &&
    credential.environment === runtimeConfig.environment &&
    credential.market === runtimeConfig.market
  );
}

export function AuthProvider({
  children,
  queryClient,
}: React.PropsWithChildren<{ queryClient: QueryClient }>) {
  const [state, dispatch] = useReducer(authReducer, initialAuthState);

  const clearLocalSession = useCallback(
    async (subject?: string) => {
      if (subject) {
        const namespace = cacheNamespace({
          app: "customer",
          environment: runtimeConfig.environment,
          issuer: runtimeConfig.oidcIssuer,
          subject,
          market: runtimeConfig.market,
        });
        try {
          await performLocalLogout(namespace, {
            clearCredential,
            wipeSubjectData: wipeSubjectPartition,
            clearTemporaryFiles: clearCustomerTemporaryFiles,
            clearQueryCache: () => queryClient.clear(),
          });
          await clearCleanupMarker();
        } catch (error) {
          await markCleanupPending(namespace).catch((markerError) =>
            recordHandledError(markerError, { operation: "cleanup-marker" }),
          );
          throw error;
        }
        return;
      }
      await clearCredential();
      queryClient.clear();
    },
    [queryClient],
  );

  const signIn = useCallback(async () => {
    dispatch({ type: "SIGN_IN_STARTED" });
    try {
      const discovery = await AuthSession.fetchDiscoveryAsync(
        runtimeConfig.oidcIssuer,
      );
      const redirectUri = AuthSession.makeRedirectUri({
        scheme: runtimeConfig.redirectScheme,
        path: "auth/callback",
      });
      const nonce = Crypto.randomUUID();
      const request = new AuthSession.AuthRequest({
        clientId: runtimeConfig.oidcClientId,
        redirectUri,
        responseType: AuthSession.ResponseType.Code,
        scopes: ["openid", "profile", "email", "offline_access"],
        usePKCE: true,
        extraParams: { nonce },
      });
      const result = await request.promptAsync(discovery);
      if (result.type !== "success") {
        dispatch({ type: "RESTORED", credential: null });
        return;
      }
      if (!request.codeVerifier)
        throw new Error("PKCE verifier was not generated.");
      const code = result.params.code;
      if (!code) throw new Error("Authorization code is missing.");
      const token = await AuthSession.exchangeCodeAsync(
        {
          clientId: runtimeConfig.oidcClientId,
          code,
          redirectUri,
          extraParams: { code_verifier: request.codeVerifier },
        },
        discovery,
      );
      const credential = credentialFromToken(token, undefined, nonce);
      await saveCredential(credential);
      dispatch({ type: "AUTHENTICATED", credential });
    } catch (error) {
      dispatch({
        type: "FAILED",
        message: error instanceof Error ? error.message : "Đăng nhập thất bại.",
      });
    }
  }, []);

  const refreshCredential = useCallback(
    async (current: CustomerCredential): Promise<CustomerCredential> => {
      if (!current.refreshToken) throw new Error("Refresh token is unavailable.");
      const discovery = await AuthSession.fetchDiscoveryAsync(
        runtimeConfig.oidcIssuer,
      );
      const token = await AuthSession.refreshAsync(
        {
          clientId: runtimeConfig.oidcClientId,
          refreshToken: current.refreshToken,
        },
        discovery,
      );
      const credential = credentialFromToken(token, current);
      await saveCredential(credential);
      return credential;
    },
    [],
  );

  const refresh = useCallback(async () => {
    if (!state.credential?.refreshToken) return;
    const current = state.credential;
    dispatch({ type: "REFRESH_STARTED" });
    try {
      const credential = await refreshCredential(current);
      dispatch({ type: "AUTHENTICATED", credential });
    } catch {
      dispatch({ type: "SIGNED_OUT" });
      await clearLocalSession(current.subject).catch((error) =>
        recordHandledError(error, { operation: "refresh-failure-wipe" }),
      );
    }
  }, [clearLocalSession, refreshCredential, state.credential]);

  useEffect(() => {
    let active = true;
    void loadCleanupMarker()
      .then(async (namespace) => {
        if (!namespace) return true;
        try {
          await performLocalLogout(namespace, {
            clearCredential,
            wipeSubjectData: wipeSubjectPartition,
            clearTemporaryFiles: clearCustomerTemporaryFiles,
            clearQueryCache: () => queryClient.clear(),
          });
          await clearCleanupMarker();
          return true;
        } catch (error) {
          recordHandledError(error, { operation: "pending-cleanup-retry" });
          return false;
        }
      })
      .catch((error) => {
        recordHandledError(error, { operation: "cleanup-marker-load" });
        return false;
      })
      .then((cleanupComplete) =>
        cleanupComplete ? loadCredential() : null,
      )
      .then(async (credential) => {
        if (!active) return;
        if (!credential) {
          dispatch({ type: "RESTORED", credential: null });
          return;
        }
        if (!credentialMatchesRuntime(credential)) {
          dispatch({ type: "RESTORED", credential: null });
          await clearLocalSession(credential.subject);
          return;
        }
        if (credential.expiresAt > Date.now() + 60_000) {
          dispatch({ type: "RESTORED", credential });
          return;
        }
        if (!credential.refreshToken) {
          dispatch({ type: "RESTORED", credential: null });
          await clearLocalSession(credential.subject);
          return;
        }
        try {
          const refreshed = await refreshCredential(credential);
          if (active) dispatch({ type: "AUTHENTICATED", credential: refreshed });
        } catch (error) {
          if (active) dispatch({ type: "RESTORED", credential: null });
          await clearLocalSession(credential.subject).catch((wipeError) =>
            recordHandledError(wipeError, { operation: "restore-failure-wipe" }),
          );
          recordHandledError(error, { operation: "restore-refresh" });
        }
      })
      .catch(() => {
        if (active) dispatch({ type: "RESTORED", credential: null });
      });
    return () => {
      active = false;
    };
  }, [clearLocalSession, queryClient, refreshCredential]);

  const signOut = useCallback(async () => {
    const subject = state.credential?.subject;
    dispatch({ type: "SIGN_OUT_STARTED" });
    try {
      await clearLocalSession(subject);
    } catch (error) {
      recordHandledError(error, { operation: "logout-wipe" });
    } finally {
      // Never retain an authenticated in-memory route after logout was requested.
      dispatch({ type: "SIGNED_OUT" });
    }
  }, [clearLocalSession, state.credential?.subject]);

  useEffect(() => {
    if (state.status !== "authenticated" || !state.credential) return;
    const refreshAt = state.credential.expiresAt - 60_000;
    const delay = Math.max(0, refreshAt - Date.now());
    const timer = setTimeout(() => {
      if (state.credential?.refreshToken) void refresh();
      else void signOut();
    }, delay);
    return () => clearTimeout(timer);
  }, [refresh, signOut, state.credential, state.status]);

  const value = useMemo(
    () => ({ ...state, signIn, refresh, signOut }),
    [refresh, signIn, signOut, state],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within AuthProvider.");
  return context;
}
