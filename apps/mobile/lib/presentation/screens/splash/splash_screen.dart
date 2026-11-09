import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:go_router/go_router.dart';
import '../../../core/constants/app_colors.dart';
import '../../../core/navigation/route_names.dart';
import '../../../core/utils/theme_ext.dart';

class SplashScreen extends StatefulWidget {
  const SplashScreen({super.key});

  @override
  State<SplashScreen> createState() => _SplashScreenState();
}

class _SplashScreenState extends State<SplashScreen>
    with SingleTickerProviderStateMixin {
  late final AnimationController _pulse;

  @override
  void initState() {
    super.initState();
    _pulse = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 2),
    )..repeat(reverse: true);

    Future.delayed(const Duration(milliseconds: 2800), () {
      if (mounted) context.go(RouteNames.onboarding);
    });
  }

  @override
  void dispose() {
    _pulse.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final gridColor = context.borderC.withValues(alpha: 0.3);

    return Scaffold(
      backgroundColor: context.appBg,
      body: Stack(
        children: [
          // Ambient glow background
          Center(
            child: AnimatedBuilder(
              animation: _pulse,
              builder: (_, __) => Container(
                width: 350,
                height: 350,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  gradient: RadialGradient(
                    colors: [
                      AppColors.primary.withValues(
                          alpha: 0.10 + _pulse.value * 0.06),
                      AppColors.accentPurple.withValues(
                          alpha: 0.05 + _pulse.value * 0.03),
                      Colors.transparent,
                    ],
                  ),
                ),
              ),
            ),
          ),

          // Grid overlay
          CustomPaint(
            painter: _GridPainter(color: gridColor),
            child: const SizedBox.expand(),
          ),

          // Content
          Center(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                _LogoMark()
                    .animate()
                    .scale(
                      begin: const Offset(0.5, 0.5),
                      end: const Offset(1.0, 1.0),
                      duration: 800.ms,
                      curve: Curves.elasticOut,
                    )
                    .fadeIn(duration: 600.ms),

                const SizedBox(height: 28),

                ShaderMask(
                  shaderCallback: (bounds) => const LinearGradient(
                    colors: AppColors.cyanGradient,
                  ).createShader(bounds),
                  child: const Text(
                    'GlucoTwin',
                    style: TextStyle(
                      color: Colors.white,
                      fontSize: 36,
                      fontWeight: FontWeight.w800,
                      letterSpacing: -1.0,
                    ),
                  ),
                )
                    .animate(delay: 400.ms)
                    .fadeIn(duration: 600.ms)
                    .slideY(
                      begin: 0.3,
                      end: 0,
                      duration: 600.ms,
                      curve: Curves.easeOutCubic,
                    ),

                const SizedBox(height: 8),

                Text(
                  'AI Diabetes Digital Twin',
                  style: TextStyle(
                    color: context.textSec.withValues(alpha: 0.7),
                    fontSize: 15,
                    fontWeight: FontWeight.w400,
                    letterSpacing: 2.0,
                  ),
                ).animate(delay: 600.ms).fadeIn(duration: 600.ms),

                const SizedBox(height: 64),

                SizedBox(
                  width: 140,
                  child: LinearProgressIndicator(
                    backgroundColor: context.borderC,
                    valueColor:
                        const AlwaysStoppedAnimation(AppColors.primary),
                    borderRadius: BorderRadius.circular(10),
                  ),
                ).animate(delay: 900.ms).fadeIn(duration: 400.ms),
              ],
            ),
          ),

          // Bottom tag
          Positioned(
            bottom: 40,
            left: 0,
            right: 0,
            child: Text(
              'Powered by Physiological AI',
              textAlign: TextAlign.center,
              style: TextStyle(
                color: context.textMut.withValues(alpha: 0.6),
                fontSize: 12,
                letterSpacing: 1.2,
              ),
            ).animate(delay: 1000.ms).fadeIn(duration: 600.ms),
          ),
        ],
      ),
    );
  }
}

class _LogoMark extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Container(
      width: 96,
      height: 96,
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: AppColors.cyanGradient,
        ),
        borderRadius: BorderRadius.circular(28),
        boxShadow: [
          BoxShadow(
            color: AppColors.primary.withValues(alpha: 0.4),
            blurRadius: 30,
            spreadRadius: 4,
          ),
          BoxShadow(
            color: AppColors.accentCyan.withValues(alpha: 0.2),
            blurRadius: 60,
            spreadRadius: 10,
          ),
        ],
      ),
      child: const Icon(
        Icons.hub_rounded,
        color: Colors.white,
        size: 48,
      ),
    );
  }
}

class _GridPainter extends CustomPainter {
  const _GridPainter({required this.color});

  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = color
      ..strokeWidth = 0.5;

    const step = 40.0;
    for (double x = 0; x <= size.width; x += step) {
      canvas.drawLine(Offset(x, 0), Offset(x, size.height), paint);
    }
    for (double y = 0; y <= size.height; y += step) {
      canvas.drawLine(Offset(0, y), Offset(size.width, y), paint);
    }
  }

  @override
  bool shouldRepaint(covariant _GridPainter old) => old.color != color;
}
