import type { DoctorRating } from '../types';

export const seedDoctorRatings: DoctorRating[] = [
  { id: 'r1', doctorId: 'DR-001', patientId: 'demo-1', score: 5, source: 'demo' },
  { id: 'r2', doctorId: 'DR-001', patientId: 'demo-2', score: 5, source: 'demo' },
  { id: 'r3', doctorId: 'DR-001', patientId: 'demo-3', score: 4, source: 'demo' },
  { id: 'r4', doctorId: 'DR-002', patientId: 'demo-4', score: 5, source: 'demo' },
  { id: 'r5', doctorId: 'DR-002', patientId: 'demo-5', score: 4, source: 'demo' },
  { id: 'r6', doctorId: 'DR-002', patientId: 'demo-6', score: 4, source: 'demo' },
  { id: 'r7', doctorId: 'DR-003', patientId: 'demo-7', score: 5, source: 'demo' },
  { id: 'r8', doctorId: 'DR-003', patientId: 'demo-8', score: 4, source: 'demo' },
  { id: 'r9', doctorId: 'DR-004', patientId: 'demo-9', score: 5, source: 'demo' },
  { id: 'r10', doctorId: 'DR-004', patientId: 'demo-10', score: 5, source: 'demo' },
  { id: 'r11', doctorId: 'DR-004', patientId: 'demo-11', score: 5, source: 'demo' },
];
