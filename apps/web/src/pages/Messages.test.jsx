// @vitest-environment jsdom
import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, expect, test } from 'vitest';
import { Messages } from './Messages';

const patient = { id: 'p1', slug: 'p1', name: 'Synthetic Patient', avatar: 'SP', age: 30, diabetesType: 'Type 1 Diabetes', usesCgm: false, currentGlucose: 0, trend: 'Stable', timeInRange: 0, averageGlucose: 0, lastReading: '', status: 'Needs Review', doctor: '', cgmStatus: 'Offline', lastActive: 'Now' };
const row = (id, text, sentAt) => ({ id, doctorId: 'd1', patientSlug: 'p1', patient: 'Synthetic Patient', avatar: 'SP', from: id === 'b' ? 'doctor' : 'patient', text, time: id === 'z' ? '11:24 PM' : 'Now', sentAt });

afterEach(cleanup);

test('conversation renders oldest to newest with deterministic timestamp ties', () => {
  render(<MemoryRouter initialEntries={['/messages?patient=p1']}><Messages role="patient" doctorId="d1" currentPatient={patient} doctorName="Doctor" patientRecords={[patient]} messages={[
    row('z', 'Newest', '2026-11-09T23:24:00Z'),
    row('b', 'Tie B', '2026-11-09T23:23:00Z'),
    row('a', 'Tie A', '2026-11-09T23:23:00Z'),
  ]} setMessages={() => {}} acceptedPatientSlugs={['p1']} assignmentStatus="accepted" /></MemoryRouter>);
  const text = screen.getByTestId('message-scroll').textContent;
  expect(text.indexOf('Tie A')).toBeLessThan(text.indexOf('Tie B'));
  expect(text.indexOf('Tie B')).toBeLessThan(text.indexOf('Newest'));
});
