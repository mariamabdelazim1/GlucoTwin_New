import type { Account, CareAssignment, Patient, PatientProfile } from '../types';
import { getPatient } from './patients';
import demoPatient from './demoPatient.json';

export const seedAccounts: Account[] = [
  {
    id: 'DR-001', role: 'doctor', email: 'sarah.ahmed@clinic.example',
    doctorProfile: {
      fullName: 'Dr. Sarah Ahmed', specialty: 'Endocrinology', yearsExperience: '12',
      medicalSchool: 'Cairo University Faculty of Medicine', qualifications: 'Endocrinology and diabetes care',
      bio: 'Focuses on continuous glucose monitoring and collaborative diabetes care.',
      certificates: ['Endocrinology specialist certification'], papers: [],
    },
  },
  {
    id: 'DR-002', role: 'doctor', email: 'khaled.mansour@clinic.example',
    doctorProfile: {
      fullName: 'Dr. Khaled Mansour', specialty: 'Diabetology', yearsExperience: '18',
      medicalSchool: 'Alexandria University Faculty of Medicine', qualifications: 'Diabetes and metabolic care',
      bio: 'Works with adults managing insulin therapy and long-term glucose patterns.',
      certificates: ['Diabetes specialist certification'], papers: [],
    },
  },
  {
    id: 'DR-003', role: 'doctor', email: 'reem.osman@clinic.example',
    doctorProfile: {
      fullName: 'Dr. Reem Osman', specialty: 'Internal Medicine', yearsExperience: '10',
      medicalSchool: 'Ain Shams University Faculty of Medicine', qualifications: 'Internal medicine and diabetes management',
      bio: 'Supports day-to-day diabetes management and coordinated follow-up.',
      certificates: ['Internal medicine specialist certification'], papers: [],
    },
  },
  {
    id: 'DR-004', role: 'doctor', email: 'nada.yassin@clinic.example',
    doctorProfile: {
      fullName: 'Dr. Nada Yassin', specialty: 'Endocrinology', yearsExperience: '14',
      medicalSchool: 'Cairo University Faculty of Medicine', qualifications: 'Endocrinology and continuous glucose monitoring',
      bio: 'Focuses on practical treatment plans informed by glucose trends.',
      certificates: ['Endocrinology specialist certification'], papers: [],
    },
  },
  {
    id: 'omar-hassan', role: 'patient', email: 'omar.hassan@example.com',
    patientProfile: {
      fullName: 'Omar Hassan', age: '34', weight: '82', height: '178', diabetesType: 'Type 1 Diabetes',
      insulinPlan: 'Basal-bolus therapy', diagnosisYear: '2012', medications: 'Insulin', allergies: 'None reported',
      emergencyContact: '', selectedDoctorId: 'DR-001',
    },
  },
];

export const seedAssignments: CareAssignment[] = [
  ...['omar-hassan', 'mariam-ali', 'layla-fathy', 'salma-tarek', 'hana-mostafa'].map((patientId): CareAssignment => ({ patientId, doctorId: 'DR-001', status: 'accepted' })),
  { patientId: 'farah-adel', doctorId: 'DR-001', status: 'pending' },
];

export function patientRecord(id: string, profile?: PatientProfile): Patient {
  const known = getPatient(id);
  if (id === demoPatient.patientId) return { ...known, ...demoPatient.summary, trend: 'Falling', status: 'In Range', usesCgm: true, cgmStatus: 'Connected', name: profile?.fullName || known.name };
  if (known.slug === id) return profile ? {
    ...known, name: profile.fullName, age: Number(profile.age) || known.age, diabetesType: profile.diabetesType || 'Not provided',
    usesCgm: false, currentGlucose: 0, timeInRange: 0, averageGlucose: 0,
    lastReading: 'No CGM connected', cgmStatus: 'Offline', status: 'Needs Review',
  } : known;
  const name = profile?.fullName || 'New patient';
  return {
    id: `PT-${id.slice(0, 8).toUpperCase()}`, slug: id, name,
    avatar: name.split(/\s+/).map((part) => part[0]).slice(0, 2).join('').toUpperCase(),
    age: Number(profile?.age) || 0, diabetesType: profile?.diabetesType || 'Not provided',
    usesCgm: false, currentGlucose: 0, trend: 'Stable', timeInRange: 0, averageGlucose: 0,
    lastReading: 'No CGM connected', status: 'Needs Review', doctor: '', cgmStatus: 'Offline', lastActive: 'Now',
  };
}
