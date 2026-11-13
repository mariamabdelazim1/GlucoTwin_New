// @vitest-environment jsdom
import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { afterEach, expect, test, vi } from 'vitest';
import App from '../App';

const response = {
  doctors: [{
    id: 'DR-001', role: 'doctor', email: 'sarah.ahmed@clinic.example',
    doctorProfile: { fullName: 'Dr. Sarah Server', specialty: 'Updated specialty', yearsExperience: '19', medicalSchool: 'Updated school', qualifications: 'Updated qualifications', bio: 'Authoritative server biography', certificates: ['Updated certificate'], papers: ['Updated paper'], documents: [] },
  }],
  ratings: [],
};

afterEach(() => {
  cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); localStorage.clear(); sessionStorage.clear();
  window.history.pushState({}, '', '/');
});

test('a fresh public directory replaces seeded profile values and fetches once', async () => {
  let doctorRequests = 0;
  vi.stubGlobal('fetch', vi.fn(async (url) => {
    if (url === '/api/doctors') { doctorRequests += 1; return { ok: true, json: async () => response }; }
    throw new Error(`Unexpected request ${url}`);
  }));
  window.history.pushState({}, '', '/doctors');
  render(<BrowserRouter><App /></BrowserRouter>);
  await waitFor(() => expect(screen.getByText('Dr. Sarah Server')).toBeTruthy());
  expect(screen.queryByText('Dr. Sarah Ahmed')).toBeNull();
  fireEvent.click(within(screen.getByText('Dr. Sarah Server').closest('article')).getByRole('button', { name: 'Profile' }));
  expect(screen.getByText('Authoritative server biography')).toBeTruthy();
  expect(screen.getByText(/Updated qualifications/)).toBeTruthy();
  expect(doctorRequests).toBe(1);
  const storedDoctor = JSON.parse(localStorage.getItem('ddt.accounts.v1')).find((item) => item.id === 'DR-001');
  expect(storedDoctor).not.toHaveProperty('password');
  expect(storedDoctor.doctorProfile.bio).toBe('Authoritative server biography');
});

test('legacy account passwords are sanitized without changing profiles or pending uploads', async () => {
  const profile = { fullName: 'Legacy Patient', age: '28', weight: '65', height: '168', diabetesType: 'Type 1 Diabetes', insulinPlan: '', diagnosisYear: '', medications: '', allergies: '', emergencyContact: '', selectedDoctorId: 'DR-001' };
  localStorage.setItem('ddt.accounts.v1', JSON.stringify([{ id: 'legacy-patient', role: 'patient', email: 'legacy@example.test', password: 'must-disappear', patientProfile: profile }]));
  const pending = [{ id: 'pending-1', patientSlug: 'legacy-patient', value: 120, syncState: 'pending' }];
  localStorage.setItem('ddt.glucose.v1', JSON.stringify(pending));
  vi.stubGlobal('fetch', vi.fn(async (url) => {
    if (url === '/api/doctors') return { ok: true, json: async () => response };
    throw new Error(`Unexpected request ${url}`);
  }));
  window.history.pushState({}, '', '/doctors');
  render(<BrowserRouter><App /></BrowserRouter>);
  await waitFor(() => {
    const account = JSON.parse(localStorage.getItem('ddt.accounts.v1')).find((item) => item.id === 'legacy-patient');
    expect(account).toEqual({ id: 'legacy-patient', role: 'patient', email: 'legacy@example.test', patientProfile: profile });
  });
  expect(JSON.parse(localStorage.getItem('ddt.glucose.v1'))).toEqual(pending);
  expect(localStorage.getItem('ddt.accounts.v1')).not.toContain('must-disappear');
});
