import type { Doctor } from '../types';

export const doctors: Doctor[] = [
  { id: 'DR-001', name: 'Dr. Sarah Ahmed', specialty: 'Endocrinology', assignedPatients: 24, status: 'Active', lastActive: 'Now' },
  { id: 'DR-002', name: 'Dr. Khaled Mansour', specialty: 'Diabetology', assignedPatients: 31, status: 'Active', lastActive: '8 min ago' },
  { id: 'DR-003', name: 'Dr. Reem Osman', specialty: 'Internal Medicine', assignedPatients: 18, status: 'Away', lastActive: '42 min ago' },
  { id: 'DR-004', name: 'Dr. Nada Yassin', specialty: 'Endocrinology', assignedPatients: 27, status: 'Active', lastActive: '13 min ago' },
  { id: 'DR-005', name: 'Dr. Tamer Fouad', specialty: 'Diabetology', assignedPatients: 21, status: 'Inactive', lastActive: '4 days ago' },
];
