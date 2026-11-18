// @vitest-environment jsdom
import React, { useState } from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, expect, test } from 'vitest';
import { PatientDashboard } from './PatientDashboard';

const patient = { id: 'p1', slug: 'p1', name: 'Synthetic Patient', avatar: 'SP', age: 30, diabetesType: 'Type 1 Diabetes', usesCgm: false, currentGlucose: 0, trend: 'Stable', timeInRange: 0, averageGlucose: 0, lastReading: '', status: 'Needs Review', doctor: '', cgmStatus: 'Offline', lastActive: 'Now' };
const patientProfile = { fullName: 'Synthetic Patient', age: '30', weight: '', height: '', diabetesType: 'Type 1 Diabetes', insulinPlan: '', diagnosisYear: '', medications: '', allergies: '', emergencyContact: '', selectedDoctorId: 'd1' };

function Harness() {
  const [bolus, setBolus] = useState([]);
  const [food, setFood] = useState([]);
  const [glucose, setGlucose] = useState([]);
  const [, setMessages] = useState([]);
  return <MemoryRouter><PatientDashboard patient={patient} doctorName="Doctor" assignmentStatus="accepted" setMessages={setMessages} foodEntries={food} setFoodEntries={setFood} bolusEntries={bolus} setBolusEntries={setBolus} glucoseEntries={glucose} setGlucoseEntries={setGlucose} patientProfile={patientProfile} /></MemoryRouter>;
}

afterEach(cleanup);

test('insulin logging omits carbs, preserves zero, and shows invalid carbs', () => {
  render(<Harness />);
  expect(screen.queryByLabelText(/pre-meal/i)).toBeNull();
  fireEvent.change(screen.getByPlaceholderText('Bolus units'), { target: { value: '2' } });
  fireEvent.click(screen.getByRole('button', { name: 'Log' }));
  expect(screen.getByText('Carbs: Not provided')).toBeTruthy();

  fireEvent.change(screen.getByLabelText('Carbs (g, optional)'), { target: { value: '0' } });
  fireEvent.change(screen.getByPlaceholderText('Bolus units'), { target: { value: '1.5' } });
  fireEvent.click(screen.getByRole('button', { name: 'Log' }));
  expect(screen.getByText('Carbs: 0g')).toBeTruthy();

  fireEvent.change(screen.getByLabelText('Carbs (g, optional)'), { target: { value: '-1' } });
  fireEvent.change(screen.getByPlaceholderText('Bolus units'), { target: { value: '1' } });
  fireEvent.click(screen.getByRole('button', { name: 'Log' }));
  expect(screen.getByRole('alert').textContent).toContain('finite, non-negative');
});

test('glucose, meal, messaging, and no-CGM states remain interactive', () => {
  render(<Harness />);

  expect(screen.getByText('No CGM connected yet')).toBeTruthy();
  fireEvent.change(screen.getByLabelText('Glucose reading in mg/dL'), { target: { value: '123' } });
  fireEvent.click(screen.getByRole('button', { name: 'Record' }));
  expect(screen.getByText('123 mg/dL')).toBeTruthy();

  fireEvent.change(screen.getByPlaceholderText('Food items'), { target: { value: 'Oats and berries' } });
  fireEvent.change(screen.getByPlaceholderText('Carbs g'), { target: { value: '42' } });
  fireEvent.change(screen.getByDisplayValue('Plan for later'), { target: { value: 'eaten' } });
  fireEvent.click(screen.getByRole('button', { name: 'Add food' }));
  expect(screen.getByText('Oats and berries')).toBeTruthy();
  expect(screen.getByText('42g carbs')).toBeTruthy();
  expect(screen.getByText('eaten')).toBeTruthy();

  fireEvent.change(screen.getByLabelText('Message or question'), { target: { value: 'Can you review lunch?' } });
  fireEvent.keyDown(screen.getByLabelText('Message or question'), { key: 'Enter' });
  expect(screen.getByText('Your message was recorded for Doctor.')).toBeTruthy();
  expect(screen.getByRole('link', { name: 'Open full messages' }).getAttribute('href')).toBe('/messages');
});
