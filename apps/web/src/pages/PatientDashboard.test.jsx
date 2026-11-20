// @vitest-environment jsdom
import React, { useState } from 'react';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, expect, test, vi } from 'vitest';
import { formatLocalDateTime, PatientDashboard } from './PatientDashboard';

const patient = { id: 'p1', slug: 'p1', name: 'Synthetic Patient', avatar: 'SP', age: 30, diabetesType: 'Type 1 Diabetes', usesCgm: false, currentGlucose: 0, trend: 'Stable', timeInRange: 0, averageGlucose: 0, lastReading: '', status: 'Needs Review', doctor: '', cgmStatus: 'Offline', lastActive: 'Now' };
const meals = [
  { id: 'planned-meal', patientSlug: 'p1', patient: 'Synthetic Patient', time: '23:55', meal: 'Lunch', items: 'Soup', carbs: '30g', announcedCarbsG: 30, consumedCarbsG: null, impact: 'Pending', status: 'planned', plannedEatingAt: '2026-11-18T23:55:00Z', actualEatingAt: null, version: 1 },
  { id: 'eaten-meal', patientSlug: 'p1', patient: 'Synthetic Patient', time: '00:05', meal: 'Dinner', items: 'Pasta', carbs: '45g', announcedCarbsG: 45, consumedCarbsG: 40, impact: 'Recorded', status: 'eaten', plannedEatingAt: '2026-11-18T23:30:00Z', actualEatingAt: '2026-11-19T00:05:00Z', version: 2 },
  { id: 'legacy-meal', patientSlug: 'p1', patient: 'Synthetic Patient', time: '18:00', meal: 'Snack', items: 'Fruit', carbs: '12g', impact: 'Recorded', status: 'Reviewed' },
];

function Harness({ initialFood = meals, initialBolus = [], focusFood = false, activePatient = patient }) {
  const [bolus, setBolus] = useState(initialBolus);
  const [food, setFood] = useState(initialFood);
  return <MemoryRouter>
    <PatientDashboard focusFood={focusFood} patient={activePatient} doctorName="Doctor" assignmentStatus="accepted" foodEntries={food} setFoodEntries={setFood} bolusEntries={bolus} setBolusEntries={setBolus} />
    <output data-testid="bolus-state">{JSON.stringify(bolus)}</output>
    <output data-testid="food-state">{JSON.stringify(food)}</output>
  </MemoryRouter>;
}

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

test('manual bolus logs units and submission time without invented meal or carbohydrate fields', () => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date('2026-11-19T11:12:00Z'));
  render(<Harness />);

  expect(screen.queryByLabelText(/related meal/i)).toBeNull();
  expect(screen.queryByLabelText(/carbs/i)).toBeNull();
  expect(screen.queryByLabelText(/dose meal/i)).toBeNull();
  fireEvent.change(screen.getByLabelText('Bolus units'), { target: { value: '2.5' } });
  fireEvent.click(screen.getByRole('button', { name: 'Log' }));

  const [entry] = JSON.parse(screen.getByTestId('bolus-state').textContent);
  expect(entry.administeredUnits).toBe(2.5);
  expect(entry.administeredAt).toBe('2026-11-19T11:12:00.000Z');
  expect(entry).not.toHaveProperty('meal');
  expect(entry).not.toHaveProperty('mealId');
  expect(entry).not.toHaveProperty('carbs');
  expect(entry).not.toHaveProperty('carbsG');
  expect(screen.getByText('2.5 U')).toBeTruthy();
  expect(screen.getByText(formatLocalDateTime(entry.administeredAt))).toBeTruthy();
});

test('manual bolus rejects blank, negative, and non-finite units and keeps legacy history readable', () => {
  render(<Harness initialBolus={[
    { id: 'legacy', patientSlug: 'p1', patient: 'Synthetic Patient', time: '13:12', meal: 'Lunch', carbs: '20g', recommended: '2 U', recorded: '2 U' },
    { id: 'dated', patientSlug: 'p1', patient: 'Synthetic Patient', time: '00:05', recorded: '3 U', administeredUnits: 3, administeredAt: '2026-11-19T00:05:00Z' },
  ]} />);

  for (const value of ['', '-1', 'Infinity']) {
    fireEvent.change(screen.getByLabelText('Bolus units'), { target: { value } });
    fireEvent.click(screen.getByRole('button', { name: 'Log' }));
    expect(screen.getByRole('alert').textContent).toContain('finite, non-negative');
  }
  expect(screen.getByText(formatLocalDateTime('2026-11-19T00:05:00Z'))).toBeTruthy();
  expect(screen.getByText('Date unavailable')).toBeTruthy();
});

test('food form creates an eaten meal with explicit zero carbs and does not alter planned meals', () => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date('2026-11-19T11:12:00Z'));
  render(<Harness />);

  expect(screen.queryByDisplayValue('Plan for later')).toBeNull();
  expect(screen.queryByPlaceholderText('Glucose')).toBeNull();
  fireEvent.change(screen.getByPlaceholderText('Food items'), { target: { value: 'Oats and berries' } });
  fireEvent.click(screen.getByRole('button', { name: 'Add food' }));
  expect(screen.getByRole('alert').textContent).toContain('Carbohydrates');

  fireEvent.change(screen.getByLabelText('Carbohydrates in grams'), { target: { value: '0' } });
  fireEvent.click(screen.getByRole('button', { name: 'Add food' }));
  const entries = JSON.parse(screen.getByTestId('food-state').textContent);
  expect(entries[0]).toMatchObject({
    items: 'Oats and berries', status: 'eaten', announcedCarbsG: 0, consumedCarbsG: 0,
    plannedEatingAt: '2026-11-19T11:12:00.000Z', actualEatingAt: '2026-11-19T11:12:00.000Z',
  });
  expect(entries[0]).not.toHaveProperty('glucose');
  expect(entries.find((entry) => entry.id === 'planned-meal')).toMatchObject({ status: 'planned', actualEatingAt: null });
});

test('food history sorts real timestamps across midnight and labels legacy dates unavailable', () => {
  render(<Harness />);
  const articles = screen.getAllByRole('article');
  expect(within(articles[0]).getByText('Dinner')).toBeTruthy();
  expect(within(articles[0]).getByText(`Eaten: ${formatLocalDateTime('2026-11-19T00:05:00Z')}`)).toBeTruthy();
  expect(within(articles[1]).getByText('Lunch')).toBeTruthy();
  expect(within(articles[1]).getByText(`Planned: ${formatLocalDateTime('2026-11-18T23:55:00Z')}`)).toBeTruthy();
  expect(within(articles[2]).getByText('Planned: Date unavailable')).toBeTruthy();
});

test('no-CGM and previously removed dashboard sections remain unchanged', () => {
  render(<Harness />);
  expect(screen.getByText('No CGM connected yet')).toBeTruthy();
  expect(screen.queryByText('Manual glucose readings')).toBeNull();
  expect(screen.queryByText('My medical info')).toBeNull();
  expect(screen.queryByText('Care-team messages')).toBeNull();
});

test('bolus recommendation prototype switches demo states and reveals matching sample inputs', () => {
  render(<Harness />);

  expect(screen.getByRole('heading', { name: 'Bolus Recommendation' })).toBeTruthy();
  expect(screen.getByText('Meal bolus estimate')).toBeTruthy();
  expect(screen.getByText('Lunch · 45 g carbs')).toBeTruthy();
  expect(screen.getByLabelText('Dose unavailable').textContent).toBe('— U');

  fireEvent.click(screen.getByRole('button', { name: 'Review details' }));
  expect(screen.getByText('Sample inputs')).toBeTruthy();
  expect(screen.getByText('45 g')).toBeTruthy();

  fireEvent.click(screen.getByRole('button', { name: 'High glucose' }));
  expect(screen.getByText('Correction bolus estimate')).toBeTruthy();
  expect(screen.getByText('Glucose above your target')).toBeTruthy();
  expect(screen.getByText('214 mg/dL · Sample reading at 23:00')).toBeTruthy();
  expect(screen.getByText('70–180 mg/dL')).toBeTruthy();
  expect(screen.getByRole('button', { name: 'High glucose' }).getAttribute('aria-pressed')).toBe('true');
});

test('Food Log route renders only the two log sections before and after new entries', () => {
  const demoPatient = {
    ...patient,
    slug: 'omar-hassan',
    usesCgm: true,
    currentGlucose: 142,
    trend: 'Falling',
    timeInRange: 79,
    lastReading: 'Sample day, 23:00',
  };
  render(<Harness focusFood activePatient={demoPatient} initialFood={[]} initialBolus={[]} />);

  expect(screen.getByRole('heading', { name: 'Food' })).toBeTruthy();
  expect(screen.getByRole('heading', { name: 'Manual bolus log' })).toBeTruthy();
  expect(document.querySelectorAll('.patient-log-region .surface')).toHaveLength(2);
  expect(screen.queryByText(/Welcome,/)).toBeNull();
  expect(screen.queryByText(/Demo patient:/)).toBeNull();
  expect(screen.queryByText('Current Glucose')).toBeNull();
  expect(screen.queryByText('Bolus Recommendation')).toBeNull();
  expect(screen.queryByText('Predicted Glucose')).toBeNull();
  expect(screen.queryByText('CGM Graph')).toBeNull();
  expect(screen.queryByText('Digital Twin Forecast Graph')).toBeNull();

  fireEvent.change(screen.getByPlaceholderText('Food items'), { target: { value: 'Rice and chicken' } });
  fireEvent.change(screen.getByLabelText('Carbohydrates in grams'), { target: { value: '45' } });
  fireEvent.click(screen.getByRole('button', { name: 'Add food' }));
  fireEvent.change(screen.getByLabelText('Bolus units'), { target: { value: '3' } });
  fireEvent.click(screen.getByRole('button', { name: 'Log' }));

  expect(screen.getByText('Rice and chicken')).toBeTruthy();
  expect(screen.getByText('3 U')).toBeTruthy();
  expect(document.querySelectorAll('.patient-log-region .surface')).toHaveLength(2);
  expect(screen.queryByText('Predicted Glucose')).toBeNull();
});
