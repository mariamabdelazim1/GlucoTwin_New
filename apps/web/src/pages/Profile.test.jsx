// @vitest-environment jsdom
import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { seedAccounts } from '../data/accounts';
import { DoctorProfile } from './DoctorProfile';

const emergencyApi = vi.hoisted(() => ({
  get: vi.fn(),
  create: vi.fn(),
  update: vi.fn(),
  remove: vi.fn(),
}));

vi.mock('../utils/sync', async (importOriginal) => ({
  ...(await importOriginal()),
  getEmergencyContacts: emergencyApi.get,
  createEmergencyContact: emergencyApi.create,
  updateEmergencyContact: emergencyApi.update,
  deleteEmergencyContact: emergencyApi.remove,
}));

const patientAccount = seedAccounts.find((account) => account.id === 'omar-hassan');

beforeEach(() => {
  emergencyApi.get.mockResolvedValue({ contacts: [] });
  emergencyApi.create.mockResolvedValue({ ok: true });
  emergencyApi.update.mockResolvedValue({ ok: true });
  emergencyApi.remove.mockResolvedValue({ ok: true });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

test('patient profile uses the portal theme and saves edited health fields', async () => {
  const onSave = vi.fn().mockResolvedValue(null);
  render(<MemoryRouter><DoctorProfile account={patientAccount} accounts={seedAccounts} ratings={[]} onSave={onSave} /></MemoryRouter>);

  expect(document.querySelector('.patient-profile-page.patient-dashboard-content')).toBeTruthy();
  expect(document.querySelector('.patient-doctor-directory')).toBeTruthy();
  fireEvent.change(screen.getByLabelText('Full name'), { target: { value: 'Omar Hassan Updated' } });
  fireEvent.change(screen.getByLabelText('Weight (kg)'), { target: { value: '83' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save profile' }));

  await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
  expect(onSave.mock.calls[0][0].patientProfile).toMatchObject({
    fullName: 'Omar Hassan Updated',
    weight: '83',
    selectedDoctorId: 'DR-001',
  });
  expect(await screen.findByRole('button', { name: 'Saved' })).toBeTruthy();
});

test('patient emergency contact form keeps validation and saves structured contacts', async () => {
  render(<MemoryRouter><DoctorProfile account={patientAccount} accounts={seedAccounts} ratings={[]} onSave={vi.fn().mockResolvedValue(null)} /></MemoryRouter>);

  await screen.findByText('No structured emergency contacts yet.');
  fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Layla Hassan' } });
  fireEvent.change(screen.getByLabelText('Relationship'), { target: { value: 'Sister' } });
  fireEvent.change(screen.getByLabelText('Phone with country code'), { target: { value: '+201001234567' } });
  fireEvent.click(screen.getByRole('button', { name: 'Add contact' }));

  await waitFor(() => expect(emergencyApi.create).toHaveBeenCalledWith({
    contactName: 'Layla Hassan',
    relationship: 'Sister',
    phoneNumber: '+201001234567',
    isPrimary: false,
  }));
  expect(emergencyApi.get).toHaveBeenCalledTimes(2);
});
