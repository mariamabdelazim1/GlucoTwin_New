// @vitest-environment jsdom
import React from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, expect, test } from 'vitest';
import { Messages } from './Messages';
import { MessageThread } from '../components/messaging/Messaging';

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

test('thread follows initial, switched, outgoing, and near-bottom messages but preserves an older reading position', () => {
  const props = { doctorName: 'Doctor', draft: '', setDraft: () => {}, onSend: () => {}, canOpenPatient: false, viewerRole: 'patient' };
  const first = row('first', 'First', '2026-11-09T23:30:00Z');
  const { rerender } = render(<MemoryRouter><MessageThread {...props} patient={patient} messages={[]} /></MemoryRouter>);
  const scroller = screen.getByTestId('message-scroll');
  let scrollHeight = 900;
  Object.defineProperties(scroller, {
    clientHeight: { configurable: true, get: () => 200 },
    scrollHeight: { configurable: true, get: () => scrollHeight },
    scrollTop: { configurable: true, writable: true, value: 0 },
  });

  rerender(<MemoryRouter><MessageThread {...props} patient={patient} messages={[first]} /></MemoryRouter>);
  expect(scroller.scrollTop).toBe(900);

  scroller.scrollTop = 400;
  fireEvent.scroll(scroller);
  scrollHeight = 1000;
  const incomingWhileReading = { ...row('second', 'Incoming while reading', '2026-11-09T23:21:00Z'), from: 'doctor' };
  rerender(<MemoryRouter><MessageThread {...props} patient={patient} messages={[first, incomingWhileReading]} /></MemoryRouter>);
  expect(scroller.scrollTop).toBe(400);

  scroller.scrollTop = 800;
  fireEvent.scroll(scroller);
  scrollHeight = 1100;
  const incomingNearBottom = { ...row('third', 'Incoming near bottom', '2026-11-09T23:22:00Z'), from: 'doctor' };
  rerender(<MemoryRouter><MessageThread {...props} patient={patient} messages={[first, incomingWhileReading, incomingNearBottom]} /></MemoryRouter>);
  expect(scroller.scrollTop).toBe(1100);

  scroller.scrollTop = 300;
  fireEvent.scroll(scroller);
  scrollHeight = 1200;
  const outgoing = { ...row('fourth', 'Outgoing', '2026-11-09T23:23:00Z'), from: 'patient', syncState: 'pending' };
  rerender(<MemoryRouter><MessageThread {...props} patient={patient} messages={[first, incomingWhileReading, incomingNearBottom, outgoing]} /></MemoryRouter>);
  expect(scroller.scrollTop).toBe(1200);

  scrollHeight = 700;
  const otherPatient = { ...patient, id: 'p2', slug: 'p2', name: 'Other Patient' };
  rerender(<MemoryRouter><MessageThread {...props} patient={otherPatient} messages={[row('other', 'Other conversation', '2026-11-09T23:24:00Z')]} /></MemoryRouter>);
  expect(scroller.scrollTop).toBe(700);
});
