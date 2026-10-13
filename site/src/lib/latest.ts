/**
 * A monotonic request guard used to discard stale async results.
 *
 * `begin()` advances the generation and returns it. `isCurrent(token)` tells
 * whether a token is still the newest. `snapshot()` reads the current
 * generation without advancing it, for requests that must not invalidate
 * their siblings (for example, loading an older page of comments).
 */
export interface LatestGuard {
  begin(): number;
  snapshot(): number;
  isCurrent(token: number): boolean;
  invalidate(): number;
}

export function createLatestGuard(): LatestGuard {
  let current = 0;
  return {
    begin: () => ++current,
    snapshot: () => current,
    isCurrent: (token: number) => token === current,
    invalidate: () => ++current,
  };
}
