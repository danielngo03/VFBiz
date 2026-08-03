import * as SecureStore from "expo-secure-store";
import {
  clearCleanupMarker,
  loadCleanupMarker,
  markCleanupPending,
} from "../../src/platform/auth/cleanup-marker";

test("persists only the retryable cleanup namespace", async () => {
  jest.spyOn(SecureStore, "setItemAsync").mockResolvedValue();
  jest.spyOn(SecureStore, "getItemAsync").mockResolvedValue("customer:dev:issuer:subject:VN:1");
  jest.spyOn(SecureStore, "deleteItemAsync").mockResolvedValue();

  await markCleanupPending("customer:dev:issuer:subject:VN:1");
  await expect(loadCleanupMarker()).resolves.toBe("customer:dev:issuer:subject:VN:1");
  await clearCleanupMarker();

  expect(SecureStore.setItemAsync).toHaveBeenCalledWith(
    "vfbiz.customer.cleanup-pending.v1",
    "customer:dev:issuer:subject:VN:1",
    expect.objectContaining({ keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY }),
  );
  expect(SecureStore.deleteItemAsync).toHaveBeenCalledWith(
    "vfbiz.customer.cleanup-pending.v1",
  );
});
