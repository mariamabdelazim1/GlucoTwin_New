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
  return <MemoryRouter><PatientDashboard patient={patient} doctorName="Doctor" assignmentStatus="accepted" setMessages={() => {}} foodEntries={[]} setFoodEntries={() => {}} bolusEntries={bolus} setBolusEntries={setBolus} glucoseEntries={[]} setGlucoseEntries={() => {}} patientProfile={patientProfile} /></MemoryRouter>;
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
