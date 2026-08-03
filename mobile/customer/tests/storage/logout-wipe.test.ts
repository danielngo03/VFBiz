import { performLocalLogout } from "../../src/platform/auth/logout";

test("logout attempts every local wipe and clears query cache", async () => {
  const dependencies = {
    clearCredential: jest.fn(async () => undefined),
    wipeSubjectData: jest.fn(async () => undefined),
    clearTemporaryFiles: jest.fn(async () => undefined),
    clearQueryCache: jest.fn(),
  };
  await performLocalLogout("customer:development:issuer:subject:VN:1", dependencies);
  expect(dependencies.clearCredential).toHaveBeenCalledTimes(1);
  expect(dependencies.wipeSubjectData).toHaveBeenCalledTimes(1);
  expect(dependencies.clearTemporaryFiles).toHaveBeenCalledTimes(1);
  expect(dependencies.clearQueryCache).toHaveBeenCalledTimes(1);
});

test("logout still attempts every wipe when one step fails", async () => {
  const dependencies = {
    clearCredential: jest.fn(async () => {
      throw new Error("synthetic secure store failure");
    }),
    wipeSubjectData: jest.fn(async () => undefined),
    clearTemporaryFiles: jest.fn(async () => undefined),
    clearQueryCache: jest.fn(),
  };
  await expect(
    performLocalLogout("customer:development:issuer:subject:VN:1", dependencies),
  ).rejects.toThrow("Local logout wipe was incomplete");
  expect(dependencies.wipeSubjectData).toHaveBeenCalledTimes(1);
  expect(dependencies.clearTemporaryFiles).toHaveBeenCalledTimes(1);
  expect(dependencies.clearQueryCache).toHaveBeenCalledTimes(1);
});
