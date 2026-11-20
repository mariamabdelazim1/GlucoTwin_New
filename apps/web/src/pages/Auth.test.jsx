// @vitest-environment jsdom
import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { BrowserRouter, MemoryRouter } from 'react-router-dom';
import { afterEach, expect, test, vi } from 'vitest';
import { Login } from './Login';
import { seedAccounts } from '../data/accounts';
import App from '../App';
import { TopHeader } from '../components/layout/TopHeader';

afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); localStorage.clear(); sessionStorage.clear(); window.history.pushState({}, '', '/'); });
const defaults = { accounts: seedAccounts, ratings: [], onSignIn: vi.fn(async () => null), onRegister: vi.fn(async () => null) };

test('doctor login uses the shared Sign in and Create account tabs', () => {
  render(<MemoryRouter initialEntries={['/login/doctor']}><Login mode="doctor" {...defaults} /></MemoryRouter>);
  expect(screen.getAllByRole('button', { name: 'Sign in' })).toHaveLength(1);
  expect(screen.getByRole('tablist', { name: 'Account action' })).toBeTruthy();
  expect(screen.getByRole('tab', { name: 'Sign in' }).getAttribute('aria-selected')).toBe('true');
  expect(screen.getByRole('tab', { name: 'Create account' })).toBeTruthy();
});

test('patient and doctor share the same account-action tab classes and responsive container', () => {
  render(<MemoryRouter initialEntries={['/login/patient']}><Login mode="patient" {...defaults} /></MemoryRouter>);
  const patientTabs = screen.getByRole('tablist', { name: 'Account action' });
  const patientClass = patientTabs.className;
  cleanup();
  render(<MemoryRouter initialEntries={['/login/doctor']}><Login mode="doctor" {...defaults} /></MemoryRouter>);
  expect(screen.getByRole('tablist', { name: 'Account action' }).className).toBe(patientClass);
});

test('doctor-registration URLs open the existing professional profile fields', () => {
  render(<MemoryRouter initialEntries={['/login/doctor?action=register']}><Login mode="doctor" {...defaults} /></MemoryRouter>);
  expect(screen.getByRole('heading', { name: 'Create a doctor account' })).toBeTruthy();
  expect(screen.getByLabelText('Full name')).toBeTruthy();
  expect(screen.getByLabelText('Specialty')).toBeTruthy();
  expect(screen.getByLabelText('Years of experience')).toBeTruthy();
  expect(screen.getByLabelText('Medical college / university')).toBeTruthy();
  expect(screen.getByLabelText('Password')).toBeTruthy();
});

test('authenticated headers omit global search while retaining notifications and profile controls', () => {
  const doctor = seedAccounts.find((account) => account.id === 'DR-001');
  const { rerender } = render(<TopHeader title="Clinical portal / dashboard" role="doctor" account={doctor} />);
  expect(screen.queryByRole('textbox', { name: 'Search' })).toBeNull();
  expect(screen.getByRole('button', { name: 'Notifications' })).toBeTruthy();
  rerender(<TopHeader title="Clinical portal / patient / dashboard" role="patient" account={seedAccounts.find((account) => account.id === 'omar-hassan')} />);
  expect(screen.queryByRole('textbox', { name: 'Search' })).toBeNull();
  expect(screen.getByRole('button', { name: 'Notifications' })).toBeTruthy();
});

test('doctor registration sends the professional profile without embedding the password', async () => {
  const onRegister = vi.fn(async () => null);
  render(<MemoryRouter initialEntries={['/login/doctor?action=register']}><Login mode="doctor" {...defaults} onRegister={onRegister} /></MemoryRouter>);
  fireEvent.change(screen.getByLabelText('Full name'), { target: { value: 'Dr. New Clinician' } });
  fireEvent.change(screen.getByLabelText('Specialty'), { target: { value: 'Endocrinology' } });
  fireEvent.change(screen.getByLabelText('Years of experience'), { target: { value: '8' } });
  fireEvent.change(screen.getByLabelText('Medical college / university'), { target: { value: 'Cairo University' } });
  fireEvent.change(screen.getByLabelText('Qualifications'), { target: { value: 'Diabetes care' } });
  fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'new.clinician@example.test' } });
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'temporary-password' } });
  fireEvent.click(screen.getByRole('button', { name: 'Create account' }));
  await waitFor(() => expect(onRegister).toHaveBeenCalledTimes(1));
  const request = onRegister.mock.calls[0][0];
  expect(request.password).toBe('temporary-password');
  expect(request.account).toMatchObject({ role: 'doctor', email: 'new.clinician@example.test', doctorProfile: { fullName: 'Dr. New Clinician', specialty: 'Endocrinology', yearsExperience: '8', medicalSchool: 'Cairo University' } });
  expect(request.account).not.toHaveProperty('password');
});

test('doctor registration keeps server failures visible for retry', async () => {
  render(<MemoryRouter initialEntries={['/login/doctor?action=register']}><Login mode="doctor" {...defaults} onRegister={vi.fn(async () => 'An account with this email already exists')} /></MemoryRouter>);
  for (const [label, value] of [['Full name', 'Dr. Duplicate'], ['Specialty', 'Endocrinology'], ['Years of experience', '3'], ['Medical college / university', 'Cairo University'], ['Email', 'duplicate@example.test'], ['Password', 'temporary-password']]) fireEvent.change(screen.getByLabelText(label), { target: { value } });
  fireEvent.click(screen.getByRole('button', { name: 'Create account' }));
  expect((await screen.findByRole('alert')).textContent).toContain('An account with this email already exists');
  expect(screen.getByLabelText('Email').value).toBe('duplicate@example.test');
});

test('patient registration separates the password from the public account', async () => {
  const onRegister = vi.fn(async () => null);
  render(<MemoryRouter initialEntries={['/login/patient?action=register']}><Login mode="patient" {...defaults} onRegister={onRegister} /></MemoryRouter>);
  fireEvent.change(screen.getByLabelText('Full name'), { target: { value: 'Synthetic Patient' } });
  fireEvent.change(screen.getByLabelText('Age'), { target: { value: '30' } });
  fireEvent.change(screen.getByLabelText('Weight (kg)'), { target: { value: '70' } });
  fireEvent.change(screen.getByLabelText('Height (cm)'), { target: { value: '170' } });
  fireEvent.click(screen.getAllByRole('button', { name: 'Choose this doctor' })[0]);
  fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'synthetic@example.test' } });
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'temporary-password' } });
  fireEvent.click(screen.getByRole('button', { name: 'Create account' }));
  await waitFor(() => expect(onRegister).toHaveBeenCalledTimes(1));
  const request = onRegister.mock.calls[0][0];
  expect(request.password).toBe('temporary-password');
  expect(request.account).not.toHaveProperty('password');
});

test('successful patient registration persists only the public account', async () => {
  let registrationBody;
  vi.stubGlobal('fetch', vi.fn(async (url, options = {}) => {
    if (url === '/api/doctors') return { ok: true, json: async () => ({ doctors: seedAccounts.filter((item) => item.role === 'doctor'), ratings: [] }) };
    if (url === '/api/auth/bridge') {
      registrationBody = JSON.parse(options.body);
      const { password: _password, ...account } = registrationBody.account;
      return { ok: true, json: async () => ({ token: 'test-token', account, assignment: null }) };
    }
    if (url === '/api/snapshot') {
      const { password: _password, ...account } = registrationBody.account;
      return { ok: true, json: async () => ({ account, doctors: seedAccounts.filter((item) => item.role === 'doctor'), patients: [account], assignments: [], food: [], bolus: [], glucose: [], messages: [], ratings: [] }) };
    }
    throw new Error(`Unexpected request ${url}`);
  }));
  window.history.pushState({}, '', '/login/patient?action=register');
  render(<BrowserRouter><App /></BrowserRouter>);
  fireEvent.change(screen.getByLabelText('Full name'), { target: { value: 'Registered Patient' } });
  fireEvent.change(screen.getByLabelText('Age'), { target: { value: '30' } });
  fireEvent.change(screen.getByLabelText('Weight (kg)'), { target: { value: '70' } });
  fireEvent.change(screen.getByLabelText('Height (cm)'), { target: { value: '170' } });
  fireEvent.click(screen.getAllByRole('button', { name: 'Choose this doctor' })[0]);
  fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'registered@example.test' } });
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'temporary-password' } });
  fireEvent.click(screen.getByRole('button', { name: 'Create account' }));
  await waitFor(() => expect(registrationBody.account.password).toBe('temporary-password'));
  await waitFor(() => {
    const stored = JSON.parse(localStorage.getItem('ddt.accounts.v1')).find((item) => item.email === 'registered@example.test');
    expect(stored).toBeTruthy();
    expect(stored).not.toHaveProperty('password');
  });
  expect(localStorage.getItem('ddt.accounts.v1')).not.toContain('temporary-password');
  expect(sessionStorage.getItem('ddt.session.v1')).not.toContain('temporary-password');
});

test('server-confirmed doctor registration persists and enters the doctor portal', async () => {
  let registrationBody;
  vi.stubGlobal('fetch', vi.fn(async (url, options = {}) => {
    if (url === '/api/doctors') return { ok: true, json: async () => ({ doctors: seedAccounts.filter((item) => item.role === 'doctor'), ratings: [] }) };
    if (url === '/api/auth/bridge') {
      registrationBody = JSON.parse(options.body);
      const { password: _password, ...account } = registrationBody.account;
      return { ok: true, json: async () => ({ token: 'doctor-token', account, assignment: null }) };
    }
    if (url === '/api/snapshot') {
      const { password: _password, ...account } = registrationBody.account;
      return { ok: true, json: async () => ({ account, doctors: [...seedAccounts.filter((item) => item.role === 'doctor'), account], patients: [], assignments: [], food: [], bolus: [], glucose: [], messages: [], ratings: [] }) };
    }
    throw new Error(`Unexpected request ${url}`);
  }));
  window.history.pushState({}, '', '/login/doctor?action=register');
  render(<BrowserRouter><App /></BrowserRouter>);
  for (const [label, value] of [['Full name', 'Dr. Registered Clinician'], ['Specialty', 'Endocrinology'], ['Years of experience', '9'], ['Medical college / university', 'Cairo University'], ['Email', 'registered.doctor@example.test'], ['Password', 'temporary-password']]) fireEvent.change(screen.getByLabelText(label), { target: { value } });
  fireEvent.click(screen.getByRole('button', { name: 'Create account' }));

  expect(await screen.findByRole('heading', { name: 'Welcome, Dr. Registered Clinician' })).toBeTruthy();
  expect(registrationBody.account.role).toBe('doctor');
  const stored = JSON.parse(localStorage.getItem('ddt.accounts.v1')).find((item) => item.email === 'registered.doctor@example.test');
  expect(stored.doctorProfile.specialty).toBe('Endocrinology');
  expect(stored).not.toHaveProperty('password');
  expect(sessionStorage.getItem('ddt.sync.token')).toBe('doctor-token');
});
