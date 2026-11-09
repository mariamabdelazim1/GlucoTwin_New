import 'package:flutter/material.dart';
import '../../../core/constants/app_colors.dart';
import '../../../core/constants/app_spacing.dart';

class GradientButton extends StatelessWidget {
  const GradientButton({
    super.key,
    required this.label,
    required this.onPressed,
    this.gradient,
    this.icon,
    this.height = 56,
    this.isLoading = false,
    this.enabled = true,
    this.fullWidth = true,
  });

  final String label;
  final VoidCallback? onPressed;
  final List<Color>? gradient;
  final IconData? icon;
  final double height;
  final bool isLoading;
  final bool enabled;
  final bool fullWidth;

  @override
  Widget build(BuildContext context) {
    final colors = gradient ?? AppColors.primaryGradient;
    return SizedBox(
      width: fullWidth ? double.infinity : null,
      height: height,
      child: DecoratedBox(
        decoration: BoxDecoration(
          gradient: enabled
              ? LinearGradient(colors: colors)
              : null,
          color: enabled ? null : AppColors.darkBorder,
          borderRadius: BorderRadius.circular(AppSpacing.radiusLg),
          boxShadow: enabled
              ? [
                  BoxShadow(
                    color: colors.first.withOpacity(0.35),
                    blurRadius: 20,
                    offset: const Offset(0, 8),
                  ),
                ]
              : null,
        ),
        child: Material(
          color: Colors.transparent,
          child: InkWell(
            onTap: enabled && !isLoading ? onPressed : null,
            borderRadius: BorderRadius.circular(AppSpacing.radiusLg),
            splashColor: Colors.white.withOpacity(0.1),
            child: Center(
              child: isLoading
                  ? const SizedBox(
                      width: 22,
                      height: 22,
                      child: CircularProgressIndicator(
                        color: Colors.white,
                        strokeWidth: 2.5,
                      ),
                    )
                  : Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        if (icon != null) ...[
                          Icon(icon, color: Colors.white, size: 20),
                          const SizedBox(width: AppSpacing.sm),
                        ],
                        Text(
                          label,
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 16,
                            fontWeight: FontWeight.w600,
                            letterSpacing: 0.3,
                          ),
                        ),
                      ],
                    ),
            ),
          ),
        ),
      ),
    );
  }
}

class OutlinedGradientButton extends StatelessWidget {
  const OutlinedGradientButton({
    super.key,
    required this.label,
    required this.onPressed,
    this.gradient,
    this.icon,
    this.height = 56,
  });

  final String label;
  final VoidCallback? onPressed;
  final List<Color>? gradient;
  final IconData? icon;
  final double height;

  @override
  Widget build(BuildContext context) {
    final colors = gradient ?? AppColors.primaryGradient;
    return SizedBox(
      width: double.infinity,
      height: height,
      child: DecoratedBox(
        decoration: BoxDecoration(
          border: Border.all(
            color: colors.first.withOpacity(0.6),
            width: 1.5,
          ),
          borderRadius: BorderRadius.circular(AppSpacing.radiusLg),
        ),
        child: Material(
          color: Colors.transparent,
          child: InkWell(
            onTap: onPressed,
            borderRadius: BorderRadius.circular(AppSpacing.radiusLg),
            child: Center(
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  if (icon != null) ...[
                    Icon(icon, color: colors.first, size: 20),
                    const SizedBox(width: AppSpacing.sm),
                  ],
                  ShaderMask(
                    shaderCallback: (bounds) =>
                        LinearGradient(colors: colors).createShader(bounds),
                    child: Text(
                      label,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 16,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
