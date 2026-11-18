// @vitest-environment jsdom
import React, { useState } from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, expect, test } from 'vitest';
import { PatientDashboard } from './PatientDashboard';

const patient = { id: 'p1', slug: 'p1', name: 'Synthetic Patient', avatar: 'SP', age: 30, diabetesType: 'Type 1 Diabetes', usesCgm: false, currentGlucose: 0, trend: 'Stable', timeInRange: 0, averageGlucose: 0, lastReading: '', status: 'Needs Review', doctor: '', cgmStatus: 'Offline', lastActive: 'Now' };
const meals = [
  { id: 'planned-meal', patientSlug: 'p1', patient: 'Synthetic Patient', time: '12:00', meal: 'Lunch', items: 'Soup', carbs: '30g', announcedCarbsG: 30, consumedCarbsG: null, impact: 'Pending', status: 'planned', plannedEatingAt: '2026-01-01T12:00:00Z', actualEatingAt: null, version: 1 },
  { id: 'eaten-meal', patientSlug: 'p1', patient: 'Synthetic Patient', time: '18:00', meal: 'Dinner', items: 'Pasta', carbs: '45g', announcedCarbsG: 45, consumedCarbsG: 40, impact: 'Recorded', status: 'eaten', plannedEatingAt: '2026-01-02T18:00:00Z', actualEatingAt: '2026-01-02T18:10:00Z', version: 2 },
  { id: 'cancelled-meal', patientSlug: 'p1', patient: 'Synthetic Patient', time: '20:00', meal: 'Snack', items: 'Fruit', carbs: '12g', announcedCarbsG: 12, consumedCarbsG: null, impact: 'Cancelled', status: 'cancelled', plannedEatingAt: '2026-01-03T20:00:00Z', actualEatingAt: null, version: 2 },
];

function Harness() {
  const [bolus, setBolus] = useState([]);
  const [food, setFood] = useState(meals);
  return <MemoryRouter><PatientDashboard patient={patient} doctorName="Doctor" assignmentStatus="accepted" foodEntries={food} setFoodEntries={setFood} bolusEntries={bolus} setBolusEntries={setBolus} /></MemoryRouter>;
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

test('linked bolus uses read-only meal context without confirming a planned meal', () => {
  render(<Harness />);
  const selector = screen.getByLabelText('Related meal');
  const options = [...selector.querySelectorAll('option')];
  expect(options.map((option) => option.value)).toEqual(['', 'eaten-meal', 'planned-meal']);
  expect(options[1].textContent).toContain('Dinner');
  expect(options[1].textContent).toContain('45g');
  expect(options[1].textContent).toContain('eaten');

  fireEvent.change(selector, { target: { value: 'planned-meal' } });
  expect(screen.getByText('Consumption has not been confirmed.')).toBeTruthy();
  expect(screen.getByText('30g')).toBeTruthy();
  expect(screen.queryByLabelText('Carbs (g, optional)')).toBeNull();
  fireEvent.change(screen.getByLabelText('Bolus units'), { target: { value: '2.5' } });
  fireEvent.click(screen.getByRole('button', { name: 'Log' }));
  expect(screen.getByText('Related meal: Lunch · planned')).toBeTruthy();
  expect(screen.getByText(/Planned 30g · Not yet consumed/)).toBeTruthy();
  expect(screen.getByRole('button', { name: 'Mark eaten' })).toBeTruthy();
});

test('meal entry and no-CGM state remain while removed dashboard sections stay absent', () => {
  render(<Harness />);

  expect(screen.getByText('No CGM connected yet')).toBeTruthy();
  expect(screen.queryByText('Manual glucose readings')).toBeNull();
  expect(screen.queryByText('My medical info')).toBeNull();
  expect(screen.queryByText('Care-team messages')).toBeNull();

  fireEvent.change(screen.getByPlaceholderText('Food items'), { target: { value: 'Oats and berries' } });
  fireEvent.change(screen.getByPlaceholderText('Carbs g'), { target: { value: '42' } });
  fireEvent.change(screen.getByDisplayValue('Plan for later'), { target: { value: 'eaten' } });
  fireEvent.click(screen.getByRole('button', { name: 'Add food' }));
  expect(screen.getByText('Oats and berries')).toBeTruthy();
  expect(screen.getByText('42g carbs')).toBeTruthy();
  expect(screen.getAllByText('eaten').length).toBeGreaterThan(0);
});
