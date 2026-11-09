import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import '../../../core/constants/app_colors.dart';
import '../../../core/constants/app_spacing.dart';

enum AiStatus { active, syncing, offline, warning }

class AiStatusChip extends StatelessWidget {
  const AiStatusChip({super.key, required this.status, this.label});

  final AiStatus status;
  final String? label;

  @override
  Widget build(BuildContext context) {
    final (color, text) = switch (status) {
      AiStatus.active => (AppColors.accentGreen, label ?? 'AI Active'),
      AiStatus.syncing => (AppColors.accentCyan, label ?? 'Syncing'),
      AiStatus.offline => (AppColors.textMutedDark, label ?? 'Offline'),
      AiStatus.warning => (AppColors.warning, label ?? 'Warning'),
    };

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        color: color.withOpacity(0.12),
        borderRadius: BorderRadius.circular(AppSpacing.radiusFull),
        border: Border.all(color: color.withOpacity(0.3)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          _Dot(color: color, animate: status == AiStatus.active || status == AiStatus.syncing),
          const SizedBox(width: 6),
          Text(
            text,
            style: TextStyle(
              color: color,
              fontSize: 12,
              fontWeight: FontWeight.w600,
              letterSpacing: 0.3,
            ),
          ),
        ],
      ),
    );
  }
}

class _Dot extends StatelessWidget {
  const _Dot({required this.color, required this.animate});

  final Color color;
  final bool animate;

  @override
  Widget build(BuildContext context) {
    Widget dot = Container(
      width: 7,
      height: 7,
      decoration: BoxDecoration(color: color, shape: BoxShape.circle),
    );

    if (!animate) return dot;

    return dot
        .animate(onPlay: (c) => c.repeat())
        .scale(
          begin: const Offset(1.0, 1.0),
          end: const Offset(1.5, 1.5),
          duration: 900.ms,
          curve: Curves.easeInOut,
        )
        .then()
        .scale(
          begin: const Offset(1.5, 1.5),
          end: const Offset(1.0, 1.0),
          duration: 900.ms,
          curve: Curves.easeInOut,
        );
  }
}

class SafetyBadge extends StatelessWidget {
  const SafetyBadge({super.key, required this.cleared});

  final bool cleared;

  @override
  Widget build(BuildContext context) {
    final color = cleared ? AppColors.accentGreen : AppColors.danger;
    final icon = cleared ? Icons.verified_rounded : Icons.warning_rounded;
    final text = cleared ? 'Safety Cleared' : 'Safety Check Failed';

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          colors: [color.withOpacity(0.15), color.withOpacity(0.05)],
        ),
        borderRadius: BorderRadius.circular(AppSpacing.radiusFull),
        border: Border.all(color: color.withOpacity(0.4)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, color: color, size: 14),
          const SizedBox(width: 6),
          Text(
            text,
            style: TextStyle(
              color: color,
              fontSize: 12,
              fontWeight: FontWeight.w600,
            ),
          ),
        ],
      ),
    );
  }
}
