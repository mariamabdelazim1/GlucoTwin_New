import type { Account } from '../types';

export function mergePublicDoctors(current: Account[], remoteDoctors: Omit<Account, 'password'>[]) {
  const remoteById = new Map(remoteDoctors.map((doctor) => [doctor.id, doctor]));
  let changed = false;
  const merged = current.map((local) => {
    const remote = remoteById.get(local.id);
    if (!remote) return local;
    remoteById.delete(local.id);
    if (local.role === remote.role && local.email === remote.email
      && JSON.stringify(local.doctorProfile) === JSON.stringify(remote.doctorProfile)) return local;
    const next = { ...remote, password: local.password } as Account;
    changed = true;
    return next;
  });
  if (remoteById.size) changed = true;
  return changed ? [...merged, ...[...remoteById.values()].map((doctor) => ({ ...doctor, password: '' } as Account))] : current;
}
