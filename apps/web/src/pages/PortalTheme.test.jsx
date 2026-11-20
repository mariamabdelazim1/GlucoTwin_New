import { describe, expect, test } from 'vitest';
import { usesBluePortalTheme } from '../App';

describe('blue portal theme routing', () => {
  test.each([
    '/dashboard',
    '/patients',
    '/patients/omar-hassan',
    '/messages',
    '/notifications',
    '/profile',
  ])('covers the doctor route %s, including direct nested views', (pathname) => {
    expect(usesBluePortalTheme('doctor', pathname)).toBe(true);
  });

  test('keeps the approved patient routes blue and leaves admin outside the portal theme', () => {
    expect(usesBluePortalTheme('patient', '/patient/dashboard')).toBe(true);
    expect(usesBluePortalTheme('patient', '/messages')).toBe(true);
    expect(usesBluePortalTheme('admin', '/admin')).toBe(false);
  });
});
