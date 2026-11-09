class PatientModel {
  final String id;
  final String name;
  final String avatarInitials;
  final int age;
  final double weight; // kg
  final double height; // cm
  final int diabetesDuration; // years
  final String cgmDevice;
  final String pumpDevice;
  final bool cgmConnected;
  final bool pumpConnected;
  final DateTime diagnosisDate;
  final double targetLow;
  final double targetHigh;
  final double a1c; // percent
  final double tir; // time in range percent
  final double avgGlucose;
  final bool adaptationComplete;
  final int adaptationDaysRemaining;

  const PatientModel({
    required this.id,
    required this.name,
    required this.avatarInitials,
    required this.age,
    required this.weight,
    required this.height,
    required this.diabetesDuration,
    required this.cgmDevice,
    required this.pumpDevice,
    required this.cgmConnected,
    required this.pumpConnected,
    required this.diagnosisDate,
    required this.targetLow,
    required this.targetHigh,
    required this.a1c,
    required this.tir,
    required this.avgGlucose,
    required this.adaptationComplete,
    required this.adaptationDaysRemaining,
  });

  String get bmi => (weight / ((height / 100) * (height / 100))).toStringAsFixed(1);
}
