import * as FileSystem from "expo-file-system/legacy";

const customerCacheDirectory = FileSystem.cacheDirectory
  ? `${FileSystem.cacheDirectory}vfbiz-customer/`
  : null;

export async function clearCustomerTemporaryFiles(): Promise<void> {
  if (!customerCacheDirectory) return;
  await FileSystem.deleteAsync(customerCacheDirectory, { idempotent: true });
}
