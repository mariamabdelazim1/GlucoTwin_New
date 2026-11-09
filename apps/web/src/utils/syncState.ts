export type SyncState = 'pending' | 'synced' | 'conflict' | 'failed';

export function mergeById<T extends { id: string; version?: number; syncState?: SyncState }>(local: T[], remote: T[]) {
  if (!remote.length) return local;
  const remoteById = new Map(remote.map((item) => [item.id, item]));
  let changed = false;
  const merged = local.map((item) => {
    const next = remoteById.get(item.id);
    if (!next) return item;
    remoteById.delete(item.id);
    if (item.syncState === 'pending' || item.syncState === 'conflict' || item.syncState === 'failed') return item;
    const replace = next.version !== undefined
      ? item.version === undefined || next.version >= item.version
      : JSON.stringify(next) !== JSON.stringify(item);
    if (replace && JSON.stringify(next) !== JSON.stringify(item)) changed = true;
    return replace ? next : item;
  });
  if (remoteById.size) changed = true;
  return changed ? [...remoteById.values(), ...merged] : local;
}

export function retryDecision(status: number | undefined, previousAttempts: number, now = Date.now()) {
  const attempts = previousAttempts + 1;
  if (status === 409) return { state: 'conflict' as const, attempts };
  if (status !== undefined && status >= 400 && status < 500 && status !== 408 && status !== 429) {
    return { state: 'failed' as const, attempts };
  }
  if (attempts >= 5) return { state: 'failed' as const, attempts };
  const delay = [2000, 5000, 15000, 30000, 60000][attempts - 1];
  return { state: 'pending' as const, attempts, nextAttemptAt: now + delay };
}
