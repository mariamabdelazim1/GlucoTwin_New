import type { Account, BolusEntry, CareAssignment, DoctorRating, FoodEntry, Message } from '../types';
export { mergeById } from './syncState.ts';
import { withoutLocalSyncMetadata } from './syncState.ts';

export interface GlucoseEntry {
  id: string;
  patientSlug: string;
  value: number;
  time: string;
  recordedAt: string;
  syncState?: 'pending' | 'synced' | 'conflict' | 'failed';
  syncAttempts?: number;
  syncNextAttemptAt?: number;
  syncError?: string;
}

export class SyncApiError extends Error {
  status: number;
  constructor(status: number, message: string) { super(message); this.status = status; }
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

export interface EmergencyContact {
  id: string;
  contactName: string;
  relationship: string;
  phoneNumber: string;
  isPrimary: boolean;
}

async function api<T>(path: string, method = 'GET', payload?: unknown): Promise<T> {
  const token = sessionStorage.getItem('ddt.sync.token');
  const response = await fetch(`/api/${path}`, {
    method,
    headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: payload ? JSON.stringify(payload) : undefined,
  });
  const result = await response.json();
  if (!response.ok) throw new SyncApiError(response.status, result.error || 'Sync request failed');
  return result as T;
}

export async function bridgeAccount(account: Account) {
  const result = await api<{ token: string; account: Omit<Account, 'password'>; assignment?: CareAssignment | null }>('auth/bridge', 'POST', { account });
  sessionStorage.setItem('ddt.sync.token', result.token);
  return result;
}

export async function loginAccount(email: string, password: string, role: 'patient' | 'doctor') {
  const result = await api<{ token: string; account: Omit<Account, 'password'> }>('auth/login', 'POST', { email, password, role });
  sessionStorage.setItem('ddt.sync.token', result.token);
  return result.account;
}

export const getSnapshot = () => api<SyncSnapshot>('snapshot');
export const updateAccountProfile = (account: Account) => api<{ account: Omit<Account, 'password'> }>('profile', 'PUT', { profile: account.patientProfile || account.doctorProfile });
export const requestCareDoctor = (doctorId: string) => api<{ assignment: CareAssignment }>('patient/doctor-request', 'POST', { doctorId });
export const syncItem = (kind: 'food' | 'bolus' | 'glucose' | 'messages', item: unknown) =>
  api<{ ok: boolean }>(kind, 'POST', withoutLocalSyncMetadata(item));
export const updateMeal = (id: string, update: unknown) => api<{ ok: boolean; meal: FoodEntry }>(`food/${encodeURIComponent(id)}`, 'PATCH', update);
export const syncAssignment = (patientId: string, status: 'accepted' | 'declined') => api<{ assignment: CareAssignment }>('assignment', 'POST', { patientId, status });
export const syncRating = (doctorId: string, score: number) => api<{ ratings: DoctorRating[] }>('rating', 'POST', { doctorId, score });
export const getEmergencyContacts = () => api<{ contacts: EmergencyContact[] }>('emergency-contacts');
export const createEmergencyContact = (contact: Omit<EmergencyContact, 'id'>) => api<{ contact: EmergencyContact }>('emergency-contacts', 'POST', contact);
export const updateEmergencyContact = (id: string, contact: Partial<Omit<EmergencyContact, 'id'>>) => api<{ contact: EmergencyContact }>(`emergency-contacts/${encodeURIComponent(id)}`, 'PUT', contact);
export const deleteEmergencyContact = (id: string) => api<{ ok: boolean }>(`emergency-contacts/${encodeURIComponent(id)}`, 'DELETE');
