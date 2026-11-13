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

export class SyncNetworkError extends Error {
  constructor() { super('The care service could not be reached.'); }
}

export class SyncResponseError extends Error {
  constructor() { super('The care service returned an invalid response.'); }
}

export class SyncStorageError extends Error {
  constructor() { super('The browser could not save the authenticated session.'); }
}

const authenticationMessages = {
  connection: 'Unable to connect to the care service. Check your connection and try again.',
  response: 'The care service returned an invalid response. Please try again.',
  storage: 'The browser could not save your session. Check browser storage settings and try again.',
  unexpected: 'Authentication could not be completed. Please try again.',
} as const;

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
  if (!account) throw new SyncResponseError();
  return account;
}

async function api<T>(path: string, method = 'GET', payload?: unknown): Promise<T> {
  let token: string | null;
  try { token = sessionStorage.getItem('ddt.sync.token'); }
  catch { throw new SyncStorageError(); }
  let response: Response;
  try {
    response = await fetch(`/api/${path}`, {
      method,
      headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: payload ? JSON.stringify(payload) : undefined,
    });
  } catch { throw new SyncNetworkError(); }
  let result: unknown;
  try { result = await response.json(); }
  catch {
    if (response.ok) throw new SyncResponseError();
    throw new SyncApiError(response.status, 'The care service rejected the request.');
  }
  if (!response.ok) {
    const message = result && typeof result === 'object' && typeof (result as { error?: unknown }).error === 'string'
      ? (result as { error: string }).error
      : 'The care service rejected the request.';
    throw new SyncApiError(response.status, message);
  }
  return result as T;
}

function validatedAuthentication(result: unknown) {
  if (!result || typeof result !== 'object' || Array.isArray(result)) throw new SyncResponseError();
  const authentication = result as { token?: unknown; account?: unknown };
  if (typeof authentication.token !== 'string' || !authentication.token.trim()) throw new SyncResponseError();
  return { token: authentication.token, account: publicAccount(authentication.account) };
}

function persistAuthenticationToken(token: string) {
  try { sessionStorage.setItem('ddt.sync.token', token); }
  catch { throw new SyncStorageError(); }
}

export async function bridgeAccount(request: PatientRegistrationRequest) {
  const result = await api<unknown>('auth/bridge', 'POST', { account: { ...request.account, password: request.password } });
  const authentication = validatedAuthentication(result);
  persistAuthenticationToken(authentication.token);
  const assignment = (result as { assignment?: CareAssignment | null }).assignment;
  return { ...authentication, assignment };
}

export async function loginAccount(request: LoginRequest) {
  const result = await api<unknown>('auth/login', 'POST', request);
  const authentication = validatedAuthentication(result);
  persistAuthenticationToken(authentication.token);
  return authentication.account;
}

export const getSnapshot = async () => {
  const result = await api<SyncSnapshot>('snapshot');
  return { ...result, account: publicAccount(result.account), doctors: result.doctors.map(publicAccount), patients: result.patients.map(publicAccount) };
};
export const updateAccountProfile = async (account: Account) => {
  const result = await api<{ account: Account }>('profile', 'PUT', { profile: account.patientProfile || account.doctorProfile });
  return { account: publicAccount(result.account) };
};

export function authenticationErrorMessage(error: unknown) {
  if (error instanceof SyncApiError) return error.message;
  if (error instanceof SyncNetworkError) return authenticationMessages.connection;
  if (error instanceof SyncResponseError) return authenticationMessages.response;
  if (error instanceof SyncStorageError) return authenticationMessages.storage;
  return authenticationMessages.unexpected;
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
