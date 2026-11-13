import type { Account, BolusEntry, CareAssignment, DoctorRating, FoodEntry, LoginRequest, Message, PatientRegistrationRequest } from '../types';
export { mergeById } from './syncState.ts';
import { withoutLocalSyncMetadata } from './syncState.ts';
import { sanitizePublicAccount } from './accountState.ts';

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
  account: Account;
  doctors: Account[];
  patients: Account[];
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

function publicAccount(value: unknown) {
  const account = sanitizePublicAccount(value);
  if (!account) throw new Error('The care service returned an invalid account.');
  return account;
}

async function api<T>(path: string, method = 'GET', payload?: unknown): Promise<T> {
  const token = sessionStorage.getItem('ddt.sync.token');
  const response = await fetch(`/api/${path}`, {
    method,
    headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: payload ? JSON.stringify(payload) : undefined,
  });
  const result = await response.json().catch(() => ({}));
  if (!response.ok) throw new SyncApiError(response.status, result.error || 'Sync request failed');
  return result as T;
}

export async function bridgeAccount(request: PatientRegistrationRequest) {
  const result = await api<{ token: string; account: Account; assignment?: CareAssignment | null }>('auth/bridge', 'POST', { account: { ...request.account, password: request.password } });
  sessionStorage.setItem('ddt.sync.token', result.token);
  return { ...result, account: publicAccount(result.account) };
}

export async function loginAccount(request: LoginRequest) {
  const result = await api<{ token: string; account: Account }>('auth/login', 'POST', request);
  sessionStorage.setItem('ddt.sync.token', result.token);
  return publicAccount(result.account);
}

export const getSnapshot = async () => {
  const result = await api<SyncSnapshot>('snapshot');
  return { ...result, account: publicAccount(result.account), doctors: result.doctors.map(publicAccount), patients: result.patients.map(publicAccount) };
};
export const updateAccountProfile = async (account: Account) => {
  const result = await api<{ account: Account }>('profile', 'PUT', { profile: account.patientProfile || account.doctorProfile });
  return { account: publicAccount(result.account) };
};

export function authenticationErrorMessage(error: unknown, connectionMessage: string) {
  return error instanceof SyncApiError ? error.message : connectionMessage;
}
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
