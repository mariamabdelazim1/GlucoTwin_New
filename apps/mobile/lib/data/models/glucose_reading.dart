class GlucoseReading {
  final DateTime timestamp;
  final double value; // mg/dL
  final bool isPredicted;
  final double? confidence; // 0–1

  const GlucoseReading({
    required this.timestamp,
    required this.value,
    this.isPredicted = false,
    this.confidence,
  });
}
