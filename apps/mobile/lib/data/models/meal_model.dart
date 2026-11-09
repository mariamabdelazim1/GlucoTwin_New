class FoodItem {
  final String name;
  final String emoji;
  final double carbsPer100g;
  final double gi; // glycemic index
  final String category;

  const FoodItem({
    required this.name,
    required this.emoji,
    required this.carbsPer100g,
    required this.gi,
    required this.category,
  });
}

class FoodRecommendation {
  final FoodItem food;
  final double safePortionGrams;
  final double estimatedCarbs;
  final String glycemicImpact; // low / moderate / high
  final String personalizedTip;
  final List<double> predictedPeak; // glucose values at 30/60/90/120 min

  const FoodRecommendation({
    required this.food,
    required this.safePortionGrams,
    required this.estimatedCarbs,
    required this.glycemicImpact,
    required this.personalizedTip,
    required this.predictedPeak,
  });
}
