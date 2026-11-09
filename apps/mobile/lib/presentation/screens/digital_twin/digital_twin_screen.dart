import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../core/constants/app_colors.dart';
import '../../../core/constants/app_spacing.dart';
import '../../widgets/common/ai_status_chip.dart';
import '../../widgets/common/glass_card.dart';

class DigitalTwinScreen extends ConsumerStatefulWidget {
  const DigitalTwinScreen({super.key});

  @override
  ConsumerState<DigitalTwinScreen> createState() => _DigitalTwinScreenState();
}

class _DigitalTwinScreenState extends ConsumerState<DigitalTwinScreen>
    with TickerProviderStateMixin {
  late final AnimationController _orbit;
  late final AnimationController _pulse;
  late final AnimationController _data;

  @override
  void initState() {
    super.initState();
    _orbit = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 8),
    )..repeat();
    _pulse = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 2000),
    )..repeat(reverse: true);
    _data = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 3),
    )..repeat();
  }

  @override
  void dispose() {
    _orbit.dispose();
    _pulse.dispose();
    _data.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.darkBackground,
      body: CustomScrollView(
        slivers: [
          SliverAppBar(
            pinned: true,
            backgroundColor: AppColors.darkBackground,
            title: const Text('Digital Twin', style: TextStyle(fontWeight: FontWeight.w700)),
            actions: [
              Container(
                margin: const EdgeInsets.only(right: 16),
                child: const AiStatusChip(status: AiStatus.active, label: 'Model Active'),
              ),
            ],
          ),
          SliverPadding(
            padding: const EdgeInsets.fromLTRB(
                AppSpacing.screenPadding, 0,
                AppSpacing.screenPadding, 100),
            sliver: SliverList(
              delegate: SliverChildListDelegate([
                // Hologram visualization
                _HologramCard(orbit: _orbit, pulse: _pulse, data: _data)
                    .animate()
                    .fadeIn(duration: 600.ms),

                const SizedBox(height: 20),

                // Model status cards
                _ModelStatusRow()
                    .animate(delay: 200.ms)
                    .fadeIn(duration: 400.ms),

                const SizedBox(height: 16),

                // Physiological parameters
                _PhysiologyCard()
                    .animate(delay: 300.ms)
                    .fadeIn(duration: 400.ms),

                const SizedBox(height: 16),

                // Data streams
                _DataStreamsCard(data: _data)
                    .animate(delay: 400.ms)
                    .fadeIn(duration: 400.ms),

                const SizedBox(height: 16),

                // Organ highlights
                _OrganStatusCard()
                    .animate(delay: 500.ms)
                    .fadeIn(duration: 400.ms),
              ]),
            ),
          ),
        ],
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────

class _HologramCard extends StatelessWidget {
  const _HologramCard({
    required this.orbit,
    required this.pulse,
    required this.data,
  });

  final AnimationController orbit;
  final AnimationController pulse;
  final AnimationController data;

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 340,
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            Color(0xFF0D1525),
            Color(0xFF0A1220),
          ],
        ),
        borderRadius: BorderRadius.circular(AppSpacing.radiusXxl),
        border: Border.all(color: AppColors.primary.withOpacity(0.2)),
      ),
      child: Stack(
        alignment: Alignment.center,
        children: [
          // Grid background
          CustomPaint(
            painter: _HolographicGridPainter(),
            child: const SizedBox.expand(),
          ),

          // Orbit rings
          AnimatedBuilder(
            animation: orbit,
            builder: (_, __) => CustomPaint(
              painter: _OrbitRingsPainter(angle: orbit.value * math.pi * 2),
              child: const SizedBox(width: 280, height: 280),
            ),
          ),

          // Body silhouette
          AnimatedBuilder(
            animation: pulse,
            builder: (_, __) => Opacity(
              opacity: 0.7 + pulse.value * 0.3,
              child: CustomPaint(
                painter: _BodySilhouettePainter(glowIntensity: pulse.value),
                child: const SizedBox(width: 100, height: 200),
              ),
            ),
          ),

          // Data particles
          AnimatedBuilder(
            animation: data,
            builder: (_, __) => CustomPaint(
              painter: _DataParticlesPainter(progress: data.value),
              child: const SizedBox.expand(),
            ),
          ),

          // Status overlay (top)
          Positioned(
            top: 16,
            left: 16,
            right: 16,
            child: Row(
              children: [
                const AiStatusChip(status: AiStatus.syncing, label: 'Syncing CGM'),
                const Spacer(),
                GlassCard(
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: const [
                      Icon(Icons.memory_rounded, color: AppColors.accentCyan, size: 14),
                      SizedBox(width: 4),
                      Text(
                        'Model v2.1',
                        style: TextStyle(
                          color: AppColors.accentCyan,
                          fontSize: 11,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),

          // Bottom metrics overlay
          Positioned(
            bottom: 16,
            left: 16,
            right: 16,
            child: GlassCard(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceAround,
                children: const [
                  _HoloMetric(label: 'Parameters', value: '847'),
                  _HoloMetricDivider(),
                  _HoloMetric(label: 'Accuracy', value: '94.2%'),
                  _HoloMetricDivider(),
                  _HoloMetric(label: 'Simulations', value: '1,204'),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _HoloMetric extends StatelessWidget {
  const _HoloMetric({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Text(
          value,
          style: const TextStyle(
            color: AppColors.accentCyan,
            fontSize: 16,
            fontWeight: FontWeight.w700,
          ),
        ),
        Text(
          label,
          style: const TextStyle(color: AppColors.textMutedDark, fontSize: 10),
        ),
      ],
    );
  }
}

class _HoloMetricDivider extends StatelessWidget {
  const _HoloMetricDivider();

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 1,
      height: 28,
      color: AppColors.darkBorder.withOpacity(0.6),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────

class _ModelStatusRow extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: _StatusCard(
            title: 'Physiological\nModel',
            status: 'Running',
            color: AppColors.accentGreen,
            icon: Icons.account_tree_rounded,
            subtitle: 'ODE Solver Active',
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: _StatusCard(
            title: 'AI Prediction\nEngine',
            status: 'Active',
            color: AppColors.primary,
            icon: Icons.psychology_rounded,
            subtitle: 'LSTM + Physics',
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: _StatusCard(
            title: 'Safety\nSimulator',
            status: 'Monitoring',
            color: AppColors.accentCyan,
            icon: Icons.security_rounded,
            subtitle: 'All clear',
          ),
        ),
      ],
    );
  }
}

class _StatusCard extends StatelessWidget {
  const _StatusCard({
    required this.title,
    required this.status,
    required this.color,
    required this.icon,
    required this.subtitle,
  });

  final String title;
  final String status;
  final Color color;
  final IconData icon;
  final String subtitle;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppColors.darkCard,
        borderRadius: BorderRadius.circular(AppSpacing.radiusXl),
        border: Border.all(color: color.withOpacity(0.2)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 32,
            height: 32,
            decoration: BoxDecoration(
              color: color.withOpacity(0.12),
              borderRadius: BorderRadius.circular(9),
            ),
            child: Icon(icon, color: color, size: 16),
          ),
          const SizedBox(height: 8),
          Text(
            title,
            style: const TextStyle(
              color: AppColors.textPrimaryDark,
              fontSize: 11,
              fontWeight: FontWeight.w600,
              height: 1.3,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            status,
            style: TextStyle(color: color, fontSize: 12, fontWeight: FontWeight.w700),
          ),
          Text(
            subtitle,
            style: const TextStyle(color: AppColors.textMutedDark, fontSize: 9),
          ),
        ],
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────

class _PhysiologyCard extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.cardPadding),
      decoration: BoxDecoration(
        color: AppColors.darkCard,
        borderRadius: BorderRadius.circular(AppSpacing.radiusXl),
        border: Border.all(color: AppColors.darkBorder),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            const Icon(Icons.biotech_rounded, color: AppColors.accentCyan, size: 18),
            const SizedBox(width: 8),
            const Text(
              'Physiological Parameters',
              style: TextStyle(
                color: AppColors.textPrimaryDark,
                fontWeight: FontWeight.w600,
                fontSize: 14,
              ),
            ),
            const Spacer(),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
              decoration: BoxDecoration(
                color: AppColors.accentGreen.withOpacity(0.1),
                borderRadius: BorderRadius.circular(100),
              ),
              child: const Text(
                'Calibrated',
                style: TextStyle(
                  color: AppColors.accentGreen,
                  fontSize: 10,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
          ]),
          const SizedBox(height: 16),
          const Divider(color: AppColors.darkDivider),
          const SizedBox(height: 12),
          Wrap(
            spacing: 10,
            runSpacing: 10,
            children: [
              _PhysioParam(label: 'ISF', value: '42 mg/dL/U', color: AppColors.primary),
              _PhysioParam(label: 'ICR', value: '1:12 g/U', color: AppColors.accentPurple),
              _PhysioParam(label: 'DIA', value: '5.0 hours', color: AppColors.accentCyan),
              _PhysioParam(label: 'TDD', value: '38.2 U/day', color: AppColors.accentGreen),
              _PhysioParam(label: 'Dawn Effect', value: 'Moderate', color: AppColors.accentAmber),
              _PhysioParam(label: 'GI Absorption', value: 'Fast', color: AppColors.warning),
            ],
          ),
        ],
      ),
    );
  }
}

class _PhysioParam extends StatelessWidget {
  const _PhysioParam({
    required this.label,
    required this.value,
    required this.color,
  });

  final String label;
  final String value;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: color.withOpacity(0.06),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: color.withOpacity(0.2)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label,
            style: const TextStyle(color: AppColors.textMutedDark, fontSize: 10),
          ),
          Text(
            value,
            style: TextStyle(
              color: color,
              fontSize: 13,
              fontWeight: FontWeight.w600,
            ),
          ),
        ],
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────

class _DataStreamsCard extends StatelessWidget {
  const _DataStreamsCard({required this.data});

  final AnimationController data;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.cardPadding),
      decoration: BoxDecoration(
        color: AppColors.darkCard,
        borderRadius: BorderRadius.circular(AppSpacing.radiusXl),
        border: Border.all(color: AppColors.darkBorder),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(children: [
            Icon(Icons.stream_rounded, color: AppColors.primary, size: 18),
            SizedBox(width: 8),
            Text(
              'Real-Time Data Streams',
              style: TextStyle(
                color: AppColors.textPrimaryDark,
                fontWeight: FontWeight.w600,
                fontSize: 14,
              ),
            ),
          ]),
          const SizedBox(height: 16),
          _StreamRow(
            label: 'CGM Readings',
            source: 'Dexcom G7',
            latency: '5 sec',
            color: AppColors.accentCyan,
            anim: data,
          ),
          const SizedBox(height: 10),
          _StreamRow(
            label: 'Insulin Delivery',
            source: 'Omnipod 5',
            latency: '30 sec',
            color: AppColors.accentPurple,
            anim: data,
          ),
          const SizedBox(height: 10),
          _StreamRow(
            label: 'Model Updates',
            source: 'GlucoTwin AI',
            latency: '1 min',
            color: AppColors.primary,
            anim: data,
          ),
          const SizedBox(height: 10),
          _StreamRow(
            label: 'Safety Checks',
            source: 'Simulator',
            latency: 'Real-time',
            color: AppColors.accentGreen,
            anim: data,
          ),
        ],
      ),
    );
  }
}

class _StreamRow extends StatelessWidget {
  const _StreamRow({
    required this.label,
    required this.source,
    required this.latency,
    required this.color,
    required this.anim,
  });

  final String label;
  final String source;
  final String latency;
  final Color color;
  final AnimationController anim;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Container(
          width: 8,
          height: 8,
          decoration: BoxDecoration(color: color, shape: BoxShape.circle),
        )
            .animate(onPlay: (c) => c.repeat(reverse: true))
            .scaleXY(begin: 0.8, end: 1.4, duration: 1000.ms),
        const SizedBox(width: 10),
        Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(label,
              style: const TextStyle(
                  color: AppColors.textPrimaryDark,
                  fontSize: 13,
                  fontWeight: FontWeight.w500)),
          Text(source,
              style: const TextStyle(
                  color: AppColors.textMutedDark, fontSize: 10)),
        ]),
        const Spacer(),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
          decoration: BoxDecoration(
            color: color.withOpacity(0.08),
            borderRadius: BorderRadius.circular(100),
          ),
          child: Text(
            latency,
            style: TextStyle(color: color, fontSize: 10, fontWeight: FontWeight.w600),
          ),
        ),
      ],
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────

class _OrganStatusCard extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.cardPadding),
      decoration: BoxDecoration(
        color: AppColors.darkCard,
        borderRadius: BorderRadius.circular(AppSpacing.radiusXl),
        border: Border.all(color: AppColors.darkBorder),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(children: [
            Icon(Icons.favorite_rounded, color: AppColors.danger, size: 18),
            SizedBox(width: 8),
            Text(
              'Organ Simulation Status',
              style: TextStyle(
                color: AppColors.textPrimaryDark,
                fontWeight: FontWeight.w600,
                fontSize: 14,
              ),
            ),
          ]),
          const SizedBox(height: 16),
          Row(children: [
            Expanded(child: _OrganChip(name: 'Pancreas', status: 'Modeled', color: AppColors.accentCyan)),
            const SizedBox(width: 10),
            Expanded(child: _OrganChip(name: 'Liver', status: 'Active', color: AppColors.accentGreen)),
            const SizedBox(width: 10),
            Expanded(child: _OrganChip(name: 'Muscles', status: 'Active', color: AppColors.primary)),
          ]),
          const SizedBox(height: 10),
          Row(children: [
            Expanded(child: _OrganChip(name: 'Adipose', status: 'Modeled', color: AppColors.accentPurple)),
            const SizedBox(width: 10),
            Expanded(child: _OrganChip(name: 'Brain', status: 'Sensing', color: AppColors.accentAmber)),
            const SizedBox(width: 10),
            Expanded(child: _OrganChip(name: 'GI Tract', status: 'Active', color: AppColors.accentGreen)),
          ]),
        ],
      ),
    );
  }
}

class _OrganChip extends StatelessWidget {
  const _OrganChip({
    required this.name,
    required this.status,
    required this.color,
  });

  final String name;
  final String status;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 10),
      decoration: BoxDecoration(
        color: color.withOpacity(0.06),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: color.withOpacity(0.2)),
      ),
      child: Column(children: [
        Text(name,
            style: const TextStyle(
                color: AppColors.textPrimaryDark,
                fontSize: 11,
                fontWeight: FontWeight.w600)),
        const SizedBox(height: 2),
        Text(status,
            style: TextStyle(color: color, fontSize: 9)),
      ]),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Custom painters for hologram effect

class _HolographicGridPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = AppColors.primary.withOpacity(0.06)
      ..strokeWidth = 0.5;

    for (double x = 0; x <= size.width; x += 20) {
      canvas.drawLine(Offset(x, 0), Offset(x, size.height), paint);
    }
    for (double y = 0; y <= size.height; y += 20) {
      canvas.drawLine(Offset(0, y), Offset(size.width, y), paint);
    }
  }

  @override
  bool shouldRepaint(covariant CustomPainter old) => false;
}

class _OrbitRingsPainter extends CustomPainter {
  const _OrbitRingsPainter({required this.angle});

  final double angle;

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final paint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1;

    // Draw orbit rings with different colors and radii
    final rings = [
      (80.0, AppColors.primary, 0.0),
      (110.0, AppColors.accentCyan, math.pi / 3),
      (130.0, AppColors.accentPurple, math.pi * 2 / 3),
    ];

    for (final (radius, color, offset) in rings) {
      paint.color = color.withOpacity(0.2);
      canvas.drawCircle(center, radius, paint);

      // Orbiting dot
      final dotAngle = angle + offset;
      final dotX = center.dx + radius * math.cos(dotAngle);
      final dotY = center.dy + radius * math.sin(dotAngle);

      final dotPaint = Paint()
        ..color = color
        ..style = PaintingStyle.fill;
      canvas.drawCircle(Offset(dotX, dotY), 4, dotPaint);

      // Glow
      final glowPaint = Paint()
        ..color = color.withOpacity(0.3)
        ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 4);
      canvas.drawCircle(Offset(dotX, dotY), 6, glowPaint);
    }
  }

  @override
  bool shouldRepaint(_OrbitRingsPainter old) => old.angle != angle;
}

class _BodySilhouettePainter extends CustomPainter {
  const _BodySilhouettePainter({required this.glowIntensity});

  final double glowIntensity;

  @override
  void paint(Canvas canvas, Size size) {
    final cx = size.width / 2;
    final paint = Paint()
      ..color = AppColors.primary.withOpacity(0.5 + glowIntensity * 0.3)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.5;

    final glowPaint = Paint()
      ..color = AppColors.primary.withOpacity(0.15 + glowIntensity * 0.1)
      ..style = PaintingStyle.fill
      ..maskFilter = MaskFilter.blur(BlurStyle.normal, 8 + glowIntensity * 4);

    // Head
    final headPath = Path()..addOval(Rect.fromCenter(
        center: Offset(cx, size.height * 0.08),
        width: size.width * 0.28,
        height: size.height * 0.14));
    canvas.drawPath(headPath, glowPaint);
    canvas.drawPath(headPath, paint);

    // Torso
    final torsoPath = Path()
      ..moveTo(cx - size.width * 0.18, size.height * 0.18)
      ..lineTo(cx - size.width * 0.22, size.height * 0.55)
      ..lineTo(cx + size.width * 0.22, size.height * 0.55)
      ..lineTo(cx + size.width * 0.18, size.height * 0.18)
      ..close();
    canvas.drawPath(torsoPath, glowPaint);
    canvas.drawPath(torsoPath, paint);

    // Legs
    final legLeft = Path()
      ..moveTo(cx - size.width * 0.18, size.height * 0.55)
      ..lineTo(cx - size.width * 0.22, size.height * 0.95)
      ..lineTo(cx - size.width * 0.06, size.height * 0.95)
      ..lineTo(cx - size.width * 0.04, size.height * 0.55)
      ..close();
    canvas.drawPath(legLeft, paint);

    final legRight = Path()
      ..moveTo(cx + size.width * 0.04, size.height * 0.55)
      ..lineTo(cx + size.width * 0.06, size.height * 0.95)
      ..lineTo(cx + size.width * 0.22, size.height * 0.95)
      ..lineTo(cx + size.width * 0.18, size.height * 0.55)
      ..close();
    canvas.drawPath(legRight, paint);

    // Glucose indicator dot (pancreas area)
    final pancreasGlow = Paint()
      ..color = AppColors.accentCyan.withOpacity(0.6 + glowIntensity * 0.4)
      ..maskFilter = MaskFilter.blur(BlurStyle.normal, 6 + glowIntensity * 3);
    canvas.drawCircle(
      Offset(cx + size.width * 0.05, size.height * 0.38),
      6,
      pancreasGlow,
    );
    canvas.drawCircle(
      Offset(cx + size.width * 0.05, size.height * 0.38),
      3,
      Paint()..color = AppColors.accentCyan,
    );
  }

  @override
  bool shouldRepaint(_BodySilhouettePainter old) =>
      old.glowIntensity != glowIntensity;
}

class _DataParticlesPainter extends CustomPainter {
  const _DataParticlesPainter({required this.progress});

  final double progress;

  @override
  void paint(Canvas canvas, Size size) {
    final rng = math.Random(42);
    for (int i = 0; i < 20; i++) {
      final x = size.width * rng.nextDouble();
      final y = size.height * ((rng.nextDouble() + progress) % 1.0);
      final opacity = (math.sin(progress * math.pi * 2 + i) + 1) / 2;

      final color = i.isEven ? AppColors.accentCyan : AppColors.primary;
      canvas.drawCircle(
        Offset(x, y),
        1.5,
        Paint()..color = color.withOpacity(opacity * 0.5),
      );
    }
  }

  @override
  bool shouldRepaint(_DataParticlesPainter old) => old.progress != progress;
}
