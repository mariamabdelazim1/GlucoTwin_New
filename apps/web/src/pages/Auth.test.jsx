// @vitest-environment jsdom
import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { BrowserRouter, MemoryRouter } from 'react-router-dom';
import { afterEach, expect, test, vi } from 'vitest';
import { Login } from './Login';
import { seedAccounts } from '../data/accounts';
import App from '../App';

afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); localStorage.clear(); sessionStorage.clear(); window.history.pushState({}, '', '/'); });
const defaults = { accounts: seedAccounts, ratings: [], onSignIn: vi.fn(async () => null), onRegister: vi.fn(async () => null) };

test('doctor login remains available without doctor self-registration', () => {
  render(<MemoryRouter initialEntries={['/login/doctor']}><Login mode="doctor" {...defaults} /></MemoryRouter>);
  expect(screen.getByRole('button', { name: 'Sign in' })).toBeTruthy();
  expect(screen.queryByRole('button', { name: 'Create account' })).toBeNull();
});

test('doctor-registration URLs explain administrator provisioning', () => {
  render(<MemoryRouter initialEntries={['/login/doctor?action=register']}><Login mode="doctor" {...defaults} /></MemoryRouter>);
  expect(screen.getByText('Doctor accounts require administrator provisioning')).toBeTruthy();
  expect(screen.getByRole('link', { name: 'Back to doctor login' }).getAttribute('href')).toBe('/login/doctor');
  expect(screen.queryByLabelText('Password')).toBeNull();
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
