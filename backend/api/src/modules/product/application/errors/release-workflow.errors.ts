export class ReleaseNotFoundError extends Error {
  constructor(
    readonly releaseKind: 'catalog' | 'commercial',
    readonly releaseId: string,
  ) {
    super(`${releaseKind} release ${releaseId} was not found.`);
    this.name = 'ReleaseNotFoundError';
  }
}

export class ReleaseConcurrencyError extends Error {
  constructor(
    readonly releaseKind: 'catalog' | 'commercial',
    readonly releaseId: string,
  ) {
    super(`${releaseKind} release ${releaseId} changed concurrently.`);
    this.name = 'ReleaseConcurrencyError';
  }
}

export class ActiveReleaseNotFoundError extends Error {
  constructor(
    readonly releaseKind: 'catalog' | 'commercial',
    readonly market: string,
  ) {
    super(`Active ${releaseKind} release for market ${market} was not found.`);
    this.name = 'ActiveReleaseNotFoundError';
  }
}
