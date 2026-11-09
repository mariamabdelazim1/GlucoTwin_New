import 'package:flutter/material.dart';
import '../constants/app_colors.dart';

extension AppThemeExt on BuildContext {
  bool get isDark => Theme.of(this).brightness == Brightness.dark;

  Color get appBg => Theme.of(this).scaffoldBackgroundColor;

  Color get cardBg =>
      isDark ? AppColors.darkCard : Colors.white;

  Color get cardBgEl =>
      isDark ? AppColors.darkCardElevated : const Color(0xFFF4F7FF);

  Color get borderC =>
      isDark ? AppColors.darkBorder : AppColors.lightBorder;

  Color get divC =>
      isDark ? AppColors.darkDivider : AppColors.lightBorder;

  Color get textPri =>
      isDark ? AppColors.textPrimaryDark : AppColors.textPrimaryLight;

  Color get textSec =>
      isDark ? AppColors.textSecondaryDark : AppColors.textSecondaryLight;

  Color get textMut =>
      isDark ? AppColors.textMutedDark : AppColors.textMutedLight;

  Color get inputFill =>
      isDark ? AppColors.darkCard : const Color(0xFFF8FAFF);
}
