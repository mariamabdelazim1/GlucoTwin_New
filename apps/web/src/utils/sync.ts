import type { Account, BolusEntry, CareAssignment, DoctorRating, FoodEntry, Message } from '../types';

export interface GlucoseEntry {
  id: string;
  patientSlug: string;
  value: number;
  time: string;
  recordedAt: string;
}

export interface SyncSnapshot {
  account: Omit<Account, 'password'>;
  doctors: Omit<Account, 'password'>[];
  patients: Omit<Account, 'password'>[];
  assignments: CareAssignment[];
  food: FoodEntry[];
  bolus: BolusEntry[];
  glucose: GlucoseEntry[];
  messages: Message[];
  ratings: DoctorRating[];
}

async function api<T>(path: string, method = 'GET', payload?: unknown): Promise<T> {
  const token = sessionStorage.getItem('ddt.sync.token');
  const response = await fetch(`/api/${path}`, {
    method,
    headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: payload ? JSON.stringify(payload) : undefined,
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'Sync request failed');
  return result as T;
}

export async function bridgeAccount(account: Account) {
  const result = await api<{ token: string }>('auth/bridge', 'POST', { account });
  sessionStorage.setItem('ddt.sync.token', result.token);
}

export async function loginAccount(email: string, password: string, role: 'patient' | 'doctor') {
  const result = await api<{ token: string; account: Omit<Account, 'password'> }>('auth/login', 'POST', { email, password, role });
  sessionStorage.setItem('ddt.sync.token', result.token);
  return result.account;
}

export const getSnapshot = () => api<SyncSnapshot>('snapshot');
export const syncItem = (kind: 'food' | 'bolus' | 'glucose' | 'messages', item: unknown) => api<{ ok: boolean }>(kind, 'POST', item);
export const syncAssignment = (patientId: string, status: 'accepted' | 'declined') => api('assignment', 'POST', { patientId, status });
export const syncRating = (doctorId: string, score: number) => api<{ ratings: DoctorRating[] }>('rating', 'POST', { doctorId, score });

export function mergeById<T extends { id: string }>(local: T[], remote: T[]) {
  const known = new Set(local.map((item) => item.id));
  return remote.length && remote.some((item) => !known.has(item.id)) ? [...remote.filter((item) => !known.has(item.id)), ...local] : local;
}
