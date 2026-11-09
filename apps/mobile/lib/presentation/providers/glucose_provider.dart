import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../data/models/glucose_reading.dart';
import '../../data/mock/mock_glucose.dart';

final currentGlucoseProvider = StateProvider<double>((ref) => mockCurrentGlucose);
final glucoseDeltaProvider = StateProvider<double>((ref) => mockGlucoseDelta);
final activeInsulinProvider = StateProvider<double>((ref) => mockActiveInsulin);
final activeCarbsProvider = StateProvider<double>((ref) => mockActiveCarbs);
final glucoseHistoryProvider = StateProvider<List<GlucoseReading>>((ref) => mockGlucoseHistory);
final glucosePredictionsProvider = StateProvider<List<GlucoseReading>>((ref) => mockGlucosePredictions);

final simulationRunningProvider = StateProvider<bool>((ref) => false);
final simulationResultsProvider = StateProvider<List<GlucoseReading>?>((ref) => null);
