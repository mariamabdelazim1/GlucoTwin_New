class BasalSegment {
  final int hour; // 0-23
  final double rate; // units/hour
  final bool aiOptimized;

  const BasalSegment({
    required this.hour,
    required this.rate,
    required this.aiOptimized,
  });
}

class BolusRecommendation {
  final double suggestedUnits;
  final double confidenceScore; // 0–1
  final bool safetyClear;
  final String safetyMessage;
  final List<double> predictedGlucose; // 30, 60, 90, 120 min
  final double correctionUnits;
  final double mealUnits;

  const BolusRecommendation({
    required this.suggestedUnits,
    required this.confidenceScore,
    required this.safetyClear,
    required this.safetyMessage,
    required this.predictedGlucose,
    required this.correctionUnits,
    required this.mealUnits,
  });
}
