import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../data/models/patient_model.dart';
import '../../data/mock/mock_patient.dart';

final patientProvider = StateProvider<PatientModel>((ref) => mockPatient);
