import { createHash, randomBytes, scryptSync, timingSafeEqual } from 'node:crypto';

export const newId = (prefix) => `${prefix}_${randomBytes(12).toString('hex')}`;

export const passwordHash = (password, salt = randomBytes(16).toString('hex')) =>
  `${salt}:${scryptSync(password, salt, 64).toString('hex')}`;

export function validPassword(password, stored) {
  try {
    const [salt, digest] = stored.split(':');
    const actual = scryptSync(password, salt, 64);
    const expected = Buffer.from(digest, 'hex');
    return actual.length === expected.length && timingSafeEqual(actual, expected);
  } catch {
    return false;
  }
}

export function finiteNonnegative(value, label) {
  if (typeof value === 'boolean' || value === null || value === undefined) {
    throw new ApiError(400, `${label} must be a finite nonnegative number`);
  }
  if (typeof value !== 'number' && typeof value !== 'string') {
    throw new ApiError(400, `${label} must be a finite nonnegative number`);
  }
  if (typeof value === 'string' && (!value.trim() || !/^(?:\d+(?:\.\d*)?|\.\d+)$/.test(value.trim()))) {
    throw new ApiError(400, `${label} must be a finite nonnegative number`);
  }
  const number = typeof value === 'number' ? value : Number(value.trim());
  if (!Number.isFinite(number) || number < 0) throw new ApiError(400, `${label} must be a finite nonnegative number`);
  return number;
}

export function optionalNumber(value, label = 'Value') {
  if (value === undefined || value === null) return null;
  return finiteNonnegative(value, label);
}

export function timestamp(value, label = 'Timestamp') {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d{1,9})?)?(?:Z|[+-]\d{2}:\d{2})$/i.test(value)) {
    throw new ApiError(400, `${label} must be a full ISO timestamp with Z or an explicit UTC offset`);
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) throw new ApiError(400, `${label} must be a valid timestamp`);
  return date.toISOString();
}

export function strictUnit(value, unit, label) {
  if (typeof value === 'number') return finiteNonnegative(value, label);
  const pattern = unit === 'g' ? /^\s*(\d+(?:\.\d+)?)\s*g\s*$/i : /^\s*(\d+(?:\.\d+)?)\s*u(?:nits?)?\s*$/i;
  if (typeof value !== 'string') throw new ApiError(400, `${label} must be numeric or an unambiguous ${unit} value`);
  const match = value.match(pattern);
  if (!match) throw new ApiError(400, `${label} must be numeric or an unambiguous ${unit} value`);
  return finiteNonnegative(match[1], label);
}

export const contentHash = (value) => createHash('sha256').update(JSON.stringify(value)).digest('hex');

const localSyncFields = ['syncState', 'syncAttempts', 'syncNextAttemptAt', 'syncError'];

export function withoutLocalSyncMetadata(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return value || {};
  const copy = { ...value };
  for (const field of localSyncFields) delete copy[field];
  return copy;
}

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}


