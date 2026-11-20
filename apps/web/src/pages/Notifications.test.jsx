// @vitest-environment jsdom
import React, { useState } from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, test } from 'vitest';
import { initialMessages } from '../data/messages';
import { messageNotificationsForViewer, Notifications } from './Notifications';

afterEach(cleanup);

function PatientHarness() {
  const [messages, setMessages] = useState(initialMessages);
  return <>
    <Notifications role="patient" accountId="omar-hassan" selectedDoctorId="DR-001" doctorName="Dr. Sarah Ahmed" visiblePatientIds={[]} messages={messages} setMessages={setMessages} />
    <output data-testid="messages-state">{JSON.stringify(messages)}</output>
  </>;
}

test('Omar sees doctor replies, his patient alerts, and system notices but not his own patient-message notification', () => {
  render(<PatientHarness />);

  expect(document.querySelector('.patient-notifications-page')).toBeTruthy();
  expect(screen.getByText('New message from Dr. Sarah Ahmed')).toBeTruthy();
  expect(screen.queryByText('New message from Omar Hassan')).toBeNull();
  expect(screen.getByText('Predicted overnight elevation')).toBeTruthy();
  expect(screen.getByText('CGM sync maintenance complete')).toBeTruthy();

  const unreadRow = screen.getByText('New message from Dr. Sarah Ahmed').closest('.notification-row');
  expect(unreadRow.classList.contains('bg-clinical-secondary')).toBe(true);
  const rowButton = unreadRow.querySelector('button');
  fireEvent.click(rowButton);
  expect(unreadRow.classList.contains('bg-white')).toBe(true);
  const messages = JSON.parse(screen.getByTestId('messages-state').textContent);
  expect(messages.find((message) => message.id === 'm2').unread).toBe(false);

  const markAll = screen.getByRole('button', { name: 'Mark all as read' });
  fireEvent.click(markAll);
  expect(markAll.disabled).toBe(true);
  expect(document.querySelectorAll('.notification-row.bg-clinical-secondary')).toHaveLength(0);
});

test('the doctor receives Omar patient messages and retains authorized clinical alerts', () => {
  render(<Notifications role="doctor" accountId="DR-001" doctorName="Dr. Sarah Ahmed" visiblePatientIds={['omar-hassan', 'mariam-ali']} messages={initialMessages} setMessages={() => {}} />);

  expect(screen.getByText('New message from Omar Hassan')).toBeTruthy();
  expect(screen.queryByText('New message from Dr. Sarah Ahmed')).toBeNull();
  const criticalBadge = screen.getByText('Critical glucose');
  expect(criticalBadge.classList.contains('bg-red-50')).toBe(true);
  expect(criticalBadge.classList.contains('text-red-700')).toBe(true);
});

test('message notifications are scoped to the actual recipient in both directions', () => {
  const messages = [
    { id: 'patient-to-doctor', doctorId: 'DR-001', patientSlug: 'omar-hassan', patient: 'Omar Hassan', avatar: 'OH', from: 'patient', text: 'Patient question', time: 'Now', unread: true, unreadFor: 'doctor' },
    { id: 'doctor-to-patient', doctorId: 'DR-001', patientSlug: 'omar-hassan', patient: 'Omar Hassan', avatar: 'OH', from: 'doctor', text: 'Doctor reply', time: 'Now', unread: true, unreadFor: 'patient' },
    { id: 'other-patient', doctorId: 'DR-001', patientSlug: 'mariam-ali', patient: 'Mariam Ali', avatar: 'MA', from: 'doctor', text: 'Private reply', time: 'Now', unread: true, unreadFor: 'patient' },
  ];
  const patientItems = messageNotificationsForViewer({ role: 'patient', accountId: 'omar-hassan', selectedDoctorId: 'DR-001', doctorName: 'Dr. Sarah Ahmed', visiblePatientIds: [], messages });
  const doctorItems = messageNotificationsForViewer({ role: 'doctor', accountId: 'DR-001', doctorName: 'Dr. Sarah Ahmed', visiblePatientIds: ['omar-hassan'], messages });

  expect(patientItems.map((item) => item.messageId)).toEqual(['doctor-to-patient']);
  expect(patientItems[0].title).toBe('New message from Dr. Sarah Ahmed');
  expect(doctorItems.map((item) => item.messageId)).toEqual(['patient-to-doctor']);
  expect(doctorItems[0].title).toBe('New message from Omar Hassan');
});
