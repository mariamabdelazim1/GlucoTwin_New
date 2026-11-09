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
  const number = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(number) || number < 0) throw new ApiError(400, `${label} must be a finite nonnegative number`);
  return number;
}

export function optionalNumber(value) {
  if (value === undefined || value === null || value === '') return null;
  const number = Number(value);
  return Number.isFinite(number) && number >= 0 ? number : null;
}

export function timestamp(value, fallback = null) {
  const date = value ? new Date(value) : fallback;
  if (!(date instanceof Date) || Number.isNaN(date.getTime())) throw new ApiError(400, 'A valid timestamp with timezone is required');
  return date.toISOString();
}

export function strictUnit(value, unit, label) {
  if (typeof value === 'number') return finiteNonnegative(value, label);
  const pattern = unit === 'g' ? /^\s*(\d+(?:\.\d+)?)\s*g\s*$/i : /^\s*(\d+(?:\.\d+)?)\s*u(?:nits?)?\s*$/i;
  const match = String(value ?? '').match(pattern);
  if (!match) throw new ApiError(400, `${label} must be numeric or an unambiguous ${unit} value`);
  return finiteNonnegative(match[1], label);
}

export const contentHash = (value) => createHash('sha256').update(JSON.stringify(value)).digest('hex');

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}


