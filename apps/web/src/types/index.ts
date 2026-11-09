export type Role = 'doctor' | 'patient' | 'admin';
export type Trend = 'Rapidly rising' | 'Rising' | 'Stable' | 'Falling' | 'Rapidly falling';
export type PatientStatus = 'In Range' | 'High' | 'Low' | 'Above Range' | 'Needs Review';

export interface Patient {
  id: string;
  slug: string;
  name: string;
  avatar: string;
  age: number;
  diabetesType: 'Type 1 Diabetes' | 'Type 2 Diabetes' | 'Not provided';
  usesCgm: boolean;
  currentGlucose: number;
  trend: Trend;
  timeInRange: number;
  averageGlucose: number;
  lastReading: string;
  status: PatientStatus;
  doctor: string;
  cgmStatus: 'Connected' | 'Intermittent' | 'Offline';
  lastActive: string;
}

export interface PatientProfile {
  fullName: string;
  age: string;
  weight: string;
  height: string;
  diabetesType: 'Type 1 Diabetes' | 'Type 2 Diabetes' | '';
  insulinPlan: string;
  diagnosisYear: string;
  medications: string;
  allergies: string;
  emergencyContact: string;
  selectedDoctorId: string;
}

export interface DoctorProfileData {
  fullName: string;
  specialty: string;
  yearsExperience: string;
  medicalSchool: string;
  qualifications: string;
  bio: string;
  certificates: string[];
  papers: string[];
  photo?: string;
  documents?: { id: string; name: string; kind: 'certificate' | 'paper'; dataUrl: string }[];
}

export interface Account {
  id: string;
  role: 'doctor' | 'patient';
  email: string;
  password: string;
  doctorProfile?: DoctorProfileData;
  patientProfile?: PatientProfile;
}

export interface CareAssignment {
  patientId: string;
  doctorId: string;
  status: 'pending' | 'accepted' | 'declined';
}

export interface DoctorRating {
  id: string;
  doctorId: string;
  patientId: string;
  score: number;
  source: 'demo' | 'patient';
}

export interface Doctor {
  id: string;
  name: string;
  specialty: string;
  assignedPatients: number;
  status: 'Active' | 'Away' | 'Inactive';
  lastActive: string;
}

export interface CgmReading {
  time: string;
  glucose: number;
}

export interface ForecastPoint {
  time: string;
  historical?: number;
  predicted?: number;
}

export interface Message {
  id: string;
  doctorId?: string;
  patientSlug: string;
  patient: string;
  avatar: string;
  from: 'patient' | 'doctor';
  text: string;
  time: string;
  unread?: boolean;
}

export interface FoodEntry {
  id: string;
  patientSlug: string;
  patient: string;
  time: string;
  meal: string;
  items: string;
  carbs: string;
  impact: string;
  status: string;
}

export interface BolusEntry {
  id: string;
  patientSlug: string;
  patient: string;
  time: string;
  meal: string;
  carbs: string;
  preMeal: string;
  recommended: string;
  recorded: string;
}

export interface NotificationItem {
  id: string;
  patientSlug?: string;
  doctorId?: string;
  group: 'Today' | 'Yesterday' | 'Earlier';
  type: 'Critical glucose' | 'Patient message' | 'Digital twin alert' | 'Patient assigned' | 'System notice';
  title: string;
  body: string;
  time: string;
  read: boolean;
}
