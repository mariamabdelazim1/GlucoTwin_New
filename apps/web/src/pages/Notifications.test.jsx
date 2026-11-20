// @vitest-environment jsdom
import React from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, test } from 'vitest';
import { Notifications } from './Notifications';

afterEach(cleanup);

test('patient notifications use blue unread styling and clear it when read', () => {
  render(<Notifications role="patient" patientId="omar-hassan" doctorId="PT-001" visiblePatientIds={[]} />);

  expect(document.querySelector('.patient-notifications-page')).toBeTruthy();
  const unreadTitle = screen.getByText('New message from Omar Hassan');
  const unreadRow = unreadTitle.closest('.notification-row');
  expect(unreadRow.classList.contains('bg-clinical-secondary')).toBe(true);

  const rowButton = unreadRow.querySelector('button');
  expect(rowButton.classList.contains('border-clinical-primary')).toBe(true);
  fireEvent.click(rowButton);
  expect(unreadRow.classList.contains('bg-white')).toBe(true);
  expect(rowButton.disabled).toBe(true);

  const markAll = screen.getByRole('button', { name: 'Mark all as read' });
  fireEvent.click(markAll);
  expect(markAll.disabled).toBe(true);
  expect(document.querySelectorAll('.notification-row.bg-clinical-secondary')).toHaveLength(0);
  expect(screen.getAllByRole('button', { name: 'Mark as read' }).every((button) => button.disabled)).toBe(true);
});

test('clinical alert severity remains red for doctor notifications', () => {
  render(<Notifications role="doctor" doctorId="DR-001" visiblePatientIds={['mariam-ali']} />);

  const criticalBadge = screen.getByText('Critical glucose');
  expect(criticalBadge.classList.contains('bg-red-50')).toBe(true);
  expect(criticalBadge.classList.contains('text-red-700')).toBe(true);
});
