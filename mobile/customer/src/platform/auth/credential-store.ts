import * as SecureStore from "expo-secure-store";
import type { CustomerCredential } from "../../domain/session/session";

const CREDENTIAL_KEY = "vfbiz.customer.credential.v1";

export async function loadCredential(): Promise<CustomerCredential | null> {
  const encoded = await SecureStore.getItemAsync(CREDENTIAL_KEY);
  if (!encoded) return null;
  try {
    const credential = JSON.parse(encoded) as CustomerCredential;
    if (
      !credential.accessToken ||
      !credential.subject ||
      !credential.expiresAt ||
      !credential.issuer ||
      !credential.clientId ||
      !credential.environment ||
      !credential.market
    )
      throw new Error("Credential is incomplete.");
    return credential;
  } catch {
    await SecureStore.deleteItemAsync(CREDENTIAL_KEY);
    return null;
  }
}

export async function saveCredential(
  credential: CustomerCredential,
): Promise<void> {
  await SecureStore.setItemAsync(CREDENTIAL_KEY, JSON.stringify(credential), {
    keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
  });
}

export async function clearCredential(): Promise<void> {
  await SecureStore.deleteItemAsync(CREDENTIAL_KEY);
}
