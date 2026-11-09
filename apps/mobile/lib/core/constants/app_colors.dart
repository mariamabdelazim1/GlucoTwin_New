import 'package:flutter/material.dart';

abstract final class AppColors {
  // ── Brand Blues ──────────────────────────────────────────────────────────
  static const Color primary = Color(0xFF3B82F6);
  static const Color primaryLight = Color(0xFF60A5FA);
  static const Color primaryDark = Color(0xFF1D4ED8);

  // ── Accents ───────────────────────────────────────────────────────────────
  static const Color accentCyan = Color(0xFF22D3EE);
  static const Color accentPurple = Color(0xFFA855F7);
  static const Color accentGreen = Color(0xFF10B981);
  static const Color accentAmber = Color(0xFFF59E0B);

  // ── Glucose Range ─────────────────────────────────────────────────────────
  static const Color glucoseVeryLow = Color(0xFFDC2626);
  static const Color glucoseLow = Color(0xFFF97316);
  static const Color glucoseInRange = Color(0xFF10B981);
  static const Color glucoseHigh = Color(0xFFF59E0B);
  static const Color glucoseVeryHigh = Color(0xFFEF4444);

  // ── Dark Theme ────────────────────────────────────────────────────────────
  static const Color darkBackground = Color(0xFF070B14);
  static const Color darkSurface = Color(0xFF0D1220);
  static const Color darkCard = Color(0xFF141C2E);
  static const Color darkCardElevated = Color(0xFF1C2540);
  static const Color darkBorder = Color(0xFF1E2D4A);
  static const Color darkDivider = Color(0xFF1A2640);

  // ── Light Theme ───────────────────────────────────────────────────────────
  static const Color lightBackground = Color(0xFFF0F4FF);
  static const Color lightSurface = Color(0xFFFFFFFF);
  static const Color lightCard = Color(0xFFFFFFFF);
  static const Color lightBorder = Color(0xFFE2E8F0);

  // ── Text Dark ─────────────────────────────────────────────────────────────
  static const Color textPrimaryDark = Color(0xFFF1F5F9);
  static const Color textSecondaryDark = Color(0xFF94A3B8);
  static const Color textMutedDark = Color(0xFF475569);

  // ── Text Light ────────────────────────────────────────────────────────────
  static const Color textPrimaryLight = Color(0xFF0F172A);
  static const Color textSecondaryLight = Color(0xFF475569);
  static const Color textMutedLight = Color(0xFF94A3B8);

  // ── Status ────────────────────────────────────────────────────────────────
  static const Color success = Color(0xFF10B981);
  static const Color warning = Color(0xFFF59E0B);
  static const Color danger = Color(0xFFEF4444);
  static const Color info = Color(0xFF3B82F6);

  // ── Gradients ─────────────────────────────────────────────────────────────
  static const List<Color> primaryGradient = [
    Color(0xFF3B82F6),
    Color(0xFF6366F1),
  ];

  static const List<Color> cyanGradient = [
    Color(0xFF22D3EE),
    Color(0xFF3B82F6),
  ];

  static const List<Color> successGradient = [
    Color(0xFF10B981),
    Color(0xFF059669),
  ];

  static const List<Color> warningGradient = [
    Color(0xFFF59E0B),
    Color(0xFFEF4444),
  ];

  static const List<Color> purpleGradient = [
    Color(0xFFA855F7),
    Color(0xFF6366F1),
  ];

  static const List<Color> darkCardGradient = [
    Color(0xFF1C2540),
    Color(0xFF141C2E),
  ];

  // ── Glass ─────────────────────────────────────────────────────────────────
  static const Color glassWhite = Color(0x14FFFFFF);
  static const Color glassBorder = Color(0x33FFFFFF);
  static const Color glassBlue = Color(0x143B82F6);
}
