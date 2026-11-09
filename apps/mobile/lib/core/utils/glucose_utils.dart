import 'package:flutter/material.dart';
import '../constants/app_colors.dart';

enum GlucoseStatus { veryLow, low, inRange, high, veryHigh }

abstract final class GlucoseUtils {
  static GlucoseStatus getStatus(double mgdl) {
    if (mgdl < 54) return GlucoseStatus.veryLow;
    if (mgdl < 70) return GlucoseStatus.low;
    if (mgdl <= 180) return GlucoseStatus.inRange;
    if (mgdl <= 250) return GlucoseStatus.high;
    return GlucoseStatus.veryHigh;
  }

  static Color getColor(double mgdl) {
    switch (getStatus(mgdl)) {
      case GlucoseStatus.veryLow:
        return AppColors.glucoseVeryLow;
      case GlucoseStatus.low:
        return AppColors.glucoseLow;
      case GlucoseStatus.inRange:
        return AppColors.glucoseInRange;
      case GlucoseStatus.high:
        return AppColors.glucoseHigh;
      case GlucoseStatus.veryHigh:
        return AppColors.glucoseVeryHigh;
    }
  }

  static String getLabel(double mgdl) {
    switch (getStatus(mgdl)) {
      case GlucoseStatus.veryLow:
        return 'Very Low';
      case GlucoseStatus.low:
        return 'Low';
      case GlucoseStatus.inRange:
        return 'In Range';
      case GlucoseStatus.high:
        return 'High';
      case GlucoseStatus.veryHigh:
        return 'Very High';
    }
  }

  static String trendArrow(double delta) {
    if (delta > 3) return '↑↑';
    if (delta > 1) return '↑';
    if (delta > 0.3) return '↗';
    if (delta > -0.3) return '→';
    if (delta > -1) return '↘';
    if (delta > -3) return '↓';
    return '↓↓';
  }

  static String formatMgDl(double value) => value.round().toString();

  static double mgDlToMmol(double mgdl) => mgdl / 18.0182;

  static double mmolToMgDl(double mmol) => mmol * 18.0182;
}
