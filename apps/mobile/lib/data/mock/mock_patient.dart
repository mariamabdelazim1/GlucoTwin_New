import '../models/patient_model.dart';

final mockPatient = PatientModel(
  id: 'pt_001',
  name: 'Alex Johnson',
  avatarInitials: 'AJ',
  age: 28,
  weight: 72.0,
  height: 175.0,
  diabetesDuration: 12,
  cgmDevice: 'Dexcom G7',
  pumpDevice: 'Omnipod 5',
  cgmConnected: true,
  pumpConnected: true,
  diagnosisDate: DateTime(2012, 3, 14),
  targetLow: 70,
  targetHigh: 180,
  a1c: 6.8,
  tir: 78.4,
  avgGlucose: 138.0,
  adaptationComplete: false,
  adaptationDaysRemaining: 6,
);
