export interface LogoutDependencies {
  clearCredential(): Promise<void>;
  wipeSubjectData(namespace: string): Promise<void>;
  clearTemporaryFiles(): Promise<void>;
  clearQueryCache(): void;
}

export async function performLocalLogout(
  namespace: string,
  dependencies: LogoutDependencies,
): Promise<void> {
  const results = await Promise.allSettled([
    dependencies.clearCredential(),
    dependencies.wipeSubjectData(namespace),
    dependencies.clearTemporaryFiles(),
  ]);
  dependencies.clearQueryCache();
  const failures = results.filter((result) => result.status === "rejected");
  if (failures.length > 0)
    throw new AggregateError(failures, "Local logout wipe was incomplete.");
}
