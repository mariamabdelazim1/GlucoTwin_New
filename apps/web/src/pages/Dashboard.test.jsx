// @vitest-environment jsdom
import React, { useState } from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, expect, test, vi } from 'vitest';
import { Dashboard } from './Dashboard';

const patient = { id: 'PT-1', slug: 'patient', name: 'Synthetic Patient', avatar: 'SP', age: 30, diabetesType: 'Type 1 Diabetes', usesCgm: false, currentGlucose: 0, trend: 'Stable', timeInRange: 0, averageGlucose: 0, lastReading: '', status: 'Needs Review', doctor: '', cgmStatus: 'Offline', lastActive: 'Now' };
const base = { doctorId: 'doctor', doctorName: 'Doctor', patientRecords: [patient], foodEntries: [], bolusEntries: [], messages: [], acceptedPatientSlugs: [], patientRequests: ['patient'] };

function Harness({ decide }) {
  const [actions, setActions] = useState({});
  const act = async (status) => {
    setActions({ 'doctor:patient': { state: 'pending', message: `${status} pending` } });
    try {
      await decide(status);
      setActions({ 'doctor:patient': { state: 'success', message: `Request ${status}.` } });
    } catch {
      setActions({ 'doctor:patient': { state: 'error', message: `Could not ${status}; request remains pending.` } });
    }
  };
  return <MemoryRouter><Dashboard {...base} assignmentActions={actions} onAcceptPatient={() => act('accepted')} onDeclinePatient={() => act('declined')} /></MemoryRouter>;
}

afterEach(cleanup);

test.each([['Accept', 'accepted'], ['Decline', 'declined']])('failed %s keeps the confirmed pending request and shows an error', async (label, status) => {
  let reject;
  const decision = new Promise((_resolve, rejectPromise) => { reject = rejectPromise; });
  const decide = vi.fn(() => decision);
  render(<Harness decide={decide} />);
  fireEvent.click(screen.getByRole('button', { name: label }));
  expect(decide).toHaveBeenCalledTimes(1);
  expect(screen.getByRole('button', { name: 'Accept' }).disabled).toBe(true);
  expect(screen.getByRole('button', { name: 'Decline' }).disabled).toBe(true);
  fireEvent.click(screen.getByRole('button', { name: label }));
  expect(decide).toHaveBeenCalledTimes(1);
  reject(new Error('network failure'));
  await waitFor(() => expect(screen.getByRole('alert').textContent).toContain(`Could not ${status}`));
  expect(screen.getByText('Synthetic Patient')).toBeTruthy();
});
