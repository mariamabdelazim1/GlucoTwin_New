import type { Account } from '../types';

export function sanitizePublicAccount(value: unknown): Account | null {
  if (!value || typeof value !== 'object') return null;
  const { password: _password, ...account } = value as Record<string, unknown>;
  if (typeof account.id !== 'string' || typeof account.email !== 'string' || (account.role !== 'doctor' && account.role !== 'patient')) return null;
  return account as unknown as Account;
}

export function sanitizeStoredAccounts(value: unknown, fallback: Account[] = []) {
  if (!Array.isArray(value)) return fallback;
  return value.map(sanitizePublicAccount).filter((account): account is Account => Boolean(account));
}

export function mergePublicDoctors(current: Account[], remoteDoctors: Account[]) {
  const sanitized = remoteDoctors.map(sanitizePublicAccount).filter((doctor): doctor is Account => Boolean(doctor));
  const remoteById = new Map(sanitized.map((doctor) => [doctor.id, doctor]));
  let changed = false;
  const merged = current.map((local) => {
    const remote = remoteById.get(local.id);
    if (!remote) return local;
    remoteById.delete(local.id);
    if (local.role === remote.role && local.email === remote.email
      && JSON.stringify(local.doctorProfile) === JSON.stringify(remote.doctorProfile)) return local;
    changed = true;
    return remote;
  });
  if (remoteById.size) changed = true;
  return changed ? [...merged, ...remoteById.values()] : current;
}
