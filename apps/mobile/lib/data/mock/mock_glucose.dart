import '../models/glucose_reading.dart';
import '../models/insulin_model.dart';
import '../models/meal_model.dart';

final now = DateTime.now();

/// Last 3 hours of CGM readings (every 5 min)
List<GlucoseReading> mockGlucoseHistory = List.generate(36, (i) {
  final t = now.subtract(Duration(minutes: (35 - i) * 5));
  const base = [
    145.0, 143.0, 140.0, 136.0, 132.0, 128.0, 126.0, 122.0, 118.0, 115.0,
    112.0, 110.0, 109.0, 108.0, 107.0, 109.0, 112.0, 118.0, 124.0, 130.0,
    136.0, 141.0, 144.0, 147.0, 149.0, 148.0, 146.0, 143.0, 140.0, 137.0,
    135.0, 133.0, 132.0, 131.0, 130.0, 129.0,
  ];
  return GlucoseReading(timestamp: t, value: base[i]);
});

/// 2-hour predictions
List<GlucoseReading> mockGlucosePredictions = [
  GlucoseReading(
    timestamp: now.add(const Duration(minutes: 30)),
    value: 124.0,
    isPredicted: true,
    confidence: 0.93,
  ),
  GlucoseReading(
    timestamp: now.add(const Duration(minutes: 60)),
    value: 118.0,
    isPredicted: true,
    confidence: 0.87,
  ),
  GlucoseReading(
    timestamp: now.add(const Duration(minutes: 90)),
    value: 115.0,
    isPredicted: true,
    confidence: 0.80,
  ),
  GlucoseReading(
    timestamp: now.add(const Duration(minutes: 120)),
    value: 114.0,
    isPredicted: true,
    confidence: 0.72,
  ),
];

const double mockCurrentGlucose = 129.0;
const double mockGlucoseDelta = -1.2; // mg/dL per 5 min
const double mockActiveInsulin = 1.4; // units
const double mockActiveCarbs = 18.0; // grams

// Weekly TIR data
final weeklyTir = <String, double>{
  'Mon': 74.0,
  'Tue': 81.0,
  'Wed': 77.0,
  'Thu': 69.0,
  'Fri': 83.0,
  'Sat': 79.0,
  'Sun': 82.0,
};

// Basal schedule
final mockBasalSchedule = [
  const BasalSegment(hour: 0, rate: 0.80, aiOptimized: true),
  const BasalSegment(hour: 1, rate: 0.75, aiOptimized: true),
  const BasalSegment(hour: 2, rate: 0.75, aiOptimized: false),
  const BasalSegment(hour: 3, rate: 0.80, aiOptimized: false),
  const BasalSegment(hour: 4, rate: 0.90, aiOptimized: true),
  const BasalSegment(hour: 5, rate: 1.05, aiOptimized: true),
  const BasalSegment(hour: 6, rate: 1.20, aiOptimized: true),
  const BasalSegment(hour: 7, rate: 1.15, aiOptimized: false),
  const BasalSegment(hour: 8, rate: 1.00, aiOptimized: false),
  const BasalSegment(hour: 9, rate: 0.95, aiOptimized: true),
  const BasalSegment(hour: 10, rate: 0.90, aiOptimized: true),
  const BasalSegment(hour: 11, rate: 0.90, aiOptimized: false),
  const BasalSegment(hour: 12, rate: 0.85, aiOptimized: false),
  const BasalSegment(hour: 13, rate: 0.85, aiOptimized: true),
  const BasalSegment(hour: 14, rate: 0.80, aiOptimized: true),
  const BasalSegment(hour: 15, rate: 0.80, aiOptimized: false),
  const BasalSegment(hour: 16, rate: 0.90, aiOptimized: true),
  const BasalSegment(hour: 17, rate: 1.00, aiOptimized: true),
  const BasalSegment(hour: 18, rate: 1.05, aiOptimized: false),
  const BasalSegment(hour: 19, rate: 1.00, aiOptimized: false),
  const BasalSegment(hour: 20, rate: 0.95, aiOptimized: true),
  const BasalSegment(hour: 21, rate: 0.90, aiOptimized: true),
  const BasalSegment(hour: 22, rate: 0.85, aiOptimized: false),
  const BasalSegment(hour: 23, rate: 0.80, aiOptimized: true),
];

// Food items
final mockFoods = const [
  FoodItem(name: 'Oatmeal', emoji: '🥣', carbsPer100g: 66.0, gi: 55, category: 'Grains'),
  FoodItem(name: 'Brown Rice', emoji: '🍚', carbsPer100g: 77.0, gi: 50, category: 'Grains'),
  FoodItem(name: 'White Bread', emoji: '🍞', carbsPer100g: 49.0, gi: 73, category: 'Grains'),
  FoodItem(name: 'Banana', emoji: '🍌', carbsPer100g: 23.0, gi: 51, category: 'Fruit'),
  FoodItem(name: 'Apple', emoji: '🍎', carbsPer100g: 14.0, gi: 36, category: 'Fruit'),
  FoodItem(name: 'Chicken Breast', emoji: '🍗', carbsPer100g: 0.0, gi: 0, category: 'Protein'),
  FoodItem(name: 'Sweet Potato', emoji: '🍠', carbsPer100g: 20.0, gi: 63, category: 'Vegetables'),
  FoodItem(name: 'Greek Yogurt', emoji: '🥛', carbsPer100g: 4.0, gi: 11, category: 'Dairy'),
  FoodItem(name: 'Pasta', emoji: '🍝', carbsPer100g: 74.0, gi: 49, category: 'Grains'),
  FoodItem(name: 'Orange Juice', emoji: '🧃', carbsPer100g: 10.0, gi: 50, category: 'Drinks'),
];
