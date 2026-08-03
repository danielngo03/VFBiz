import * as SecureStore from "expo-secure-store";

const CLEANUP_MARKER_KEY = "vfbiz.customer.cleanup-pending.v1";

export async function markCleanupPending(namespace: string): Promise<void> {
  await SecureStore.setItemAsync(CLEANUP_MARKER_KEY, namespace, {
    keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
  });
}

export async function loadCleanupMarker(): Promise<string | null> {
  return SecureStore.getItemAsync(CLEANUP_MARKER_KEY);
}

export async function clearCleanupMarker(): Promise<void> {
  await SecureStore.deleteItemAsync(CLEANUP_MARKER_KEY);
}
