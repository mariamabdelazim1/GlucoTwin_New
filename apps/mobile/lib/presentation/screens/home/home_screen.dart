import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../../core/constants/app_colors.dart';
import '../../../core/constants/app_spacing.dart';
import '../../../core/navigation/route_names.dart';
import '../../../core/utils/glucose_utils.dart';
import '../../../core/utils/theme_ext.dart';
import '../../../data/mock/mock_patient.dart';
import '../../../data/models/glucose_reading.dart';
import '../../../data/models/patient_model.dart';
import '../../providers/glucose_provider.dart';
import '../../providers/patient_provider.dart';
import '../../widgets/charts/glucose_chart.dart';
import '../../widgets/common/glass_card.dart';

class HomeScreen extends ConsumerWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final glucose = ref.watch(currentGlucoseProvider);
    final delta = ref.watch(glucoseDeltaProvider);
    final insulin = ref.watch(activeInsulinProvider);
    final carbs = ref.watch(activeCarbsProvider);
    final history = ref.watch(glucoseHistoryProvider);
    final predictions = ref.watch(glucosePredictionsProvider);
    final patient = ref.watch(patientProvider);

    return Scaffold(
      backgroundColor: context.appBg,
      body: CustomScrollView(
        slivers: [
          // App bar
          _HomeAppBar(patient: patient),

          SliverPadding(
            padding: EdgeInsets.fromLTRB(
              AppSpacing.screenPadding,
              0,
              AppSpacing.screenPadding,
              AppSpacing.screenPadding + 20,
            ),
            sliver: SliverList(
              delegate: SliverChildListDelegate([
                // Main glucose card
                _GlucoseHeroCard(
                  glucose: glucose,
                  delta: delta,
                  predictions: predictions,
                  adaptationComplete: patient.adaptationComplete,
                  adaptationDaysRemaining: patient.adaptationDaysRemaining,
                ).animate().fadeIn(duration: 400.ms).slideY(begin: 0.1, end: 0),

                const SizedBox(height: 16),

                // Chart
                _ChartCard(history: history, predictions: predictions)
                    .animate(delay: 100.ms)
                    .fadeIn(duration: 400.ms),

                const SizedBox(height: 16),

                // Active insulin + carbs
                Row(
                  children: [
                    Expanded(
                      child: _MetricCard(
                        label: 'Active Insulin',
                        value: '${insulin.toStringAsFixed(1)} U',
                        icon: Icons.water_drop_rounded,
                        color: AppColors.accentPurple,
                        subtitle: '~45 min remaining',
                      ).animate(delay: 200.ms).fadeIn(duration: 400.ms),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: _MetricCard(
                        label: 'Active Carbs',
                        value: '${carbs.round()} g',
                        icon: Icons.grain_rounded,
                        color: AppColors.accentAmber,
                        subtitle: 'Absorbing now',
                      ).animate(delay: 250.ms).fadeIn(duration: 400.ms),
                    ),
                  ],
                ),

                const SizedBox(height: 12),

                // Heart Rate + Calories (moved from Daily Summary)
                Row(
                  children: [
                    Expanded(
                      child: _MetricCard(
                        label: 'Heart Rate',
                        value: '74 bpm',
                        icon: Icons.favorite_rounded,
                        color: AppColors.danger,
                        subtitle: 'Resting',
                      ).animate(delay: 270.ms).fadeIn(duration: 400.ms),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: _MetricCard(
                        label: 'Stress Level',
                        value: 'Low',
                        icon: Icons.self_improvement_rounded,
                        color: AppColors.accentGreen,
                        subtitle: 'Based on HRV',
                      ).animate(delay: 290.ms).fadeIn(duration: 400.ms),
                    ),
                  ],
                ),

                const SizedBox(height: 16),

                // Time in Range card
                _TirCard(tir: patient.tir)
                    .animate(delay: 300.ms)
                    .fadeIn(duration: 400.ms),

                const SizedBox(height: 16),

                // Quick actions
                _QuickActions()
                    .animate(delay: 380.ms)
                    .fadeIn(duration: 400.ms),

                const SizedBox(height: 16),

                // Daily summary
                _DailySummary()
                    .animate(delay: 430.ms)
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

class _HomeAppBar extends StatelessWidget {
  const _HomeAppBar({required this.patient});

  final PatientModel patient;

  @override
  Widget build(BuildContext context) {
    return SliverAppBar(
      pinned: true,
      backgroundColor: context.appBg,
      elevation: 0,
      toolbarHeight: 66,
      titleSpacing: AppSpacing.screenPadding,
      automaticallyImplyLeading: false,
      title: Row(
        children: [
          // Greeting + name
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                _greeting(),
                style: TextStyle(
                  color: context.textSec,
                  fontSize: 12,
                  fontWeight: FontWeight.w400,
                ),
              ),
              Text(
                patient.name.split(' ').first,
                style: TextStyle(
                  color: context.textPri,
                  fontSize: 19,
                  fontWeight: FontWeight.w700,
                  height: 1.2,
                ),
              ),
            ],
          ),
          const Spacer(),
          // Notification bell
          GestureDetector(
            onTap: () => context.push(RouteNames.notifications),
            child: Container(
              width: 40,
              height: 40,
              decoration: BoxDecoration(
                color: context.cardBg,
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: context.borderC),
              ),
              child: Stack(
                alignment: Alignment.center,
                children: [
                  Icon(Icons.notifications_outlined,
                      color: context.textSec, size: 20),
                  Positioned(
                    top: 8,
                    right: 8,
                    child: Container(
                      width: 7,
                      height: 7,
                      decoration: const BoxDecoration(
                        color: AppColors.danger,
                        shape: BoxShape.circle,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(width: 8),
          // Avatar
          Container(
            width: 40,
            height: 40,
            decoration: BoxDecoration(
              gradient: const LinearGradient(colors: AppColors.primaryGradient),
              borderRadius: BorderRadius.circular(12),
            ),
            alignment: Alignment.center,
            child: Text(
              patient.avatarInitials,
              style: const TextStyle(
                color: Colors.white,
                fontWeight: FontWeight.w700,
                fontSize: 13,
              ),
            ),
          ),
        ],
      ),
    );
  }

  String _greeting() {
    final hour = DateTime.now().hour;
    if (hour < 12) return 'Good morning,';
    if (hour < 17) return 'Good afternoon,';
    return 'Good evening,';
  }
}

// ─────────────────────────────────────────────────────────────────────────────

class _AdaptationCircle extends StatelessWidget {
  const _AdaptationCircle({
    required this.adaptationComplete,
    required this.adaptationDaysRemaining,
  });

  final bool adaptationComplete;
  final int adaptationDaysRemaining;

  double get _progress {
    if (adaptationComplete) return 1.0;
    const totalDays = 14;
    return ((totalDays - adaptationDaysRemaining) / totalDays).clamp(0.0, 1.0);
  }

  @override
  Widget build(BuildContext context) {
    final pct = (_progress * 100).round();
    final color = adaptationComplete ? AppColors.accentGreen : AppColors.primary;
    final centerLabel = adaptationComplete ? '✓' : '$pct%';

    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        SizedBox(
          width: 76,
          height: 76,
          child: Stack(
            alignment: Alignment.center,
            children: [
              SizedBox(
                width: 76,
                height: 76,
                child: CircularProgressIndicator(
                  value: _progress,
                  backgroundColor: context.borderC,
                  valueColor: AlwaysStoppedAnimation(color),
                  strokeWidth: 4.5,
                ),
              ),
              Text(
                centerLabel,
                style: TextStyle(
                  color: color,
                  fontSize: 20,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 3),
        Text(
          'Adapted',
          style: TextStyle(
            color: context.textMut,
            fontSize: 9,
          ),
        ),
      ],
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────

class _GlucoseHeroCard extends StatelessWidget {
  const _GlucoseHeroCard({
    required this.glucose,
    required this.delta,
    required this.predictions,
    required this.adaptationComplete,
    required this.adaptationDaysRemaining,
  });

  final double glucose;
  final double delta;
  final List<GlucoseReading> predictions;
  final bool adaptationComplete;
  final int adaptationDaysRemaining;

  @override
  Widget build(BuildContext context) {
    final status = GlucoseUtils.getStatus(glucose);
    final color = GlucoseUtils.getColor(glucose);
    final label = GlucoseUtils.getLabel(glucose);
    final arrow = GlucoseUtils.trendArrow(delta);

    return Container(
      padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.cardPadding, vertical: 14),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            context.cardBgEl,
            context.cardBg,
          ],
        ),
        borderRadius: BorderRadius.circular(AppSpacing.radiusXxl),
        border: Border.all(color: color.withOpacity(0.25)),
        boxShadow: [
          BoxShadow(
            color: color.withOpacity(0.12),
            blurRadius: 24,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      child: Column(
        children: [
          // Header + glucose in a Stack so the adaptation circle
          // floats at top-right without inflating the column spacing.
          Stack(
            clipBehavior: Clip.none,
            children: [
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  // "In Range" badge
                  Container(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                    decoration: BoxDecoration(
                      color: color.withValues(alpha: 0.12),
                      borderRadius: BorderRadius.circular(100),
                      border: Border.all(color: color.withValues(alpha: 0.3)),
                    ),
                    child: Text(
                      label,
                      style: TextStyle(
                        color: color,
                        fontSize: 11,
                        fontWeight: FontWeight.w600,
                        letterSpacing: 0.5,
                      ),
                    ),
                  ),

                  const SizedBox(height: 10),

                  // Glucose value
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.end,
                    children: [
                      Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            'Current Glucose',
                            style: TextStyle(
                              color: context.textSec,
                              fontSize: 12,
                              letterSpacing: 0.5,
                            ),
                          ),
                          const SizedBox(height: 4),
                          Row(
                            crossAxisAlignment: CrossAxisAlignment.center,
                            children: [
                              Text(
                                GlucoseUtils.formatMgDl(glucose),
                                style: TextStyle(
                                  color: color,
                                  fontSize: 60,
                                  fontWeight: FontWeight.w800,
                                  height: 1.0,
                                  letterSpacing: -2,
                                ),
                              )
                                  .animate(
                                      onPlay: (c) => c.repeat(reverse: true))
                                  .shimmer(
                                      duration: 3000.ms,
                                      color: color.withValues(alpha: 0.3)),
                              const SizedBox(width: 8),
                              Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(
                                    arrow,
                                    style: TextStyle(
                                      color: color,
                                      fontSize: 20,
                                      fontWeight: FontWeight.w700,
                                    ),
                                  ),
                                  Text(
                                    'mg/dL',
                                    style: TextStyle(
                                      color: context.textSec,
                                      fontSize: 13,
                                    ),
                                  ),
                                ],
                              ),
                            ],
                          ),
                          Text(
                            '${delta > 0 ? '+' : ''}${delta.toStringAsFixed(1)} mg/dL · 5 min',
                            style: TextStyle(
                              color: delta > 0
                                  ? AppColors.glucoseHigh
                                  : AppColors.glucoseInRange,
                              fontSize: 12,
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                ],
              ),

              // Adaptation circle positioned at top-right — not part of flow
              Positioned(
                top: 0,
                right: 0,
                child: _AdaptationCircle(
                  adaptationComplete: adaptationComplete,
                  adaptationDaysRemaining: adaptationDaysRemaining,
                ),
              ),
            ],
          ),

          const SizedBox(height: 12),
          Divider(color: context.divC),
          const SizedBox(height: 10),

          // Predictions
          Text(
            'Glucose Prediction',
            style: TextStyle(
              color: context.textSec,
              fontSize: 12,
              letterSpacing: 0.5,
            ),
          ),
          const SizedBox(height: 8),
          Row(
            children: [
              _PredictionBubble(time: '+30m', value: 124, confidence: 0.93),
              const SizedBox(width: 8),
              _PredictionBubble(time: '+1h', value: 118, confidence: 0.87),
              const SizedBox(width: 8),
              _PredictionBubble(time: '+2h', value: 114, confidence: 0.72),
            ],
          ),
        ],
      ),
    );
  }
}

class _PredictionBubble extends StatelessWidget {
  const _PredictionBubble({
    required this.time,
    required this.value,
    required this.confidence,
  });

  final String time;
  final int value;
  final double confidence;

  @override
  Widget build(BuildContext context) {
    final color = GlucoseUtils.getColor(value.toDouble());
    return Expanded(
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 10),
        decoration: BoxDecoration(
          color: color.withOpacity(0.08),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: color.withOpacity(0.2)),
        ),
        child: Column(
          children: [
            Text(
              time,
              style: TextStyle(
                color: context.textMut,
                fontSize: 10,
                fontWeight: FontWeight.w500,
              ),
            ),
            const SizedBox(height: 2),
            Text(
              '$value',
              style: TextStyle(
                color: color,
                fontSize: 18,
                fontWeight: FontWeight.w700,
              ),
            ),
            Text(
              '${(confidence * 100).round()}%',
              style: TextStyle(
                color: context.textMut.withOpacity(0.7),
                fontSize: 9,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────

class _ChartCard extends StatelessWidget {
  const _ChartCard({required this.history, required this.predictions});

  final List<GlucoseReading> history;
  final List<GlucoseReading> predictions;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.fromLTRB(12, 16, 12, 12),
      decoration: BoxDecoration(
        color: context.cardBg,
        borderRadius: BorderRadius.circular(AppSpacing.radiusXl),
        border: Border.all(color: context.borderC),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.only(left: 8, bottom: 12),
            child: Row(
              children: [
                Text(
                  'Glucose Trend',
                  style: TextStyle(
                    color: context.textPri,
                    fontWeight: FontWeight.w600,
                    fontSize: 13,
                  ),
                ),
                const Spacer(),
                // Legend
                Row(children: [
                  Container(width: 16, height: 2.5, color: AppColors.primary),
                  const SizedBox(width: 4),
                  Text('CGM',
                      style:
                          TextStyle(color: context.textMut, fontSize: 10)),
                  const SizedBox(width: 10),
                  Container(
                    width: 16,
                    height: 2.5,
                    color: AppColors.accentCyan.withOpacity(0.8),
                  ),
                  const SizedBox(width: 4),
                  Text('Prediction',
                      style:
                          TextStyle(color: context.textMut, fontSize: 10)),
                ]),
              ],
            ),
          ),
          GlucoseLineChart(
              history: history, predictions: predictions, height: 180),
        ],
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────

class _MetricCard extends StatelessWidget {
  const _MetricCard({
    required this.label,
    required this.value,
    required this.icon,
    required this.color,
    required this.subtitle,
  });

  final String label;
  final String value;
  final IconData icon;
  final Color color;
  final String subtitle;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: context.cardBg,
        borderRadius: BorderRadius.circular(AppSpacing.radiusXl),
        border: Border.all(color: context.borderC),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 36,
            height: 36,
            decoration: BoxDecoration(
              color: color.withOpacity(0.12),
              borderRadius: BorderRadius.circular(10),
            ),
            child: Icon(icon, color: color, size: 18),
          ),
          const SizedBox(height: 12),
          Text(
            value,
            style: TextStyle(
              color: context.textPri,
              fontSize: 20,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 2),
          Text(
            label,
            style: TextStyle(
              color: context.textSec,
              fontSize: 12,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            subtitle,
            style: TextStyle(
              color: context.textMut.withOpacity(0.8),
              fontSize: 10,
            ),
          ),
        ],
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────

class _TirCard extends StatelessWidget {
  const _TirCard({required this.tir});

  final double tir;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: context.cardBg,
        borderRadius: BorderRadius.circular(AppSpacing.radiusXl),
        border: Border.all(color: context.borderC),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            const Icon(Icons.track_changes_rounded,
                color: AppColors.accentGreen, size: 18),
            const SizedBox(width: 6),
            Text('Time in Range',
                style: TextStyle(color: context.textSec, fontSize: 12)),
          ]),
          const SizedBox(height: 10),
          _TirBar(tir: tir),
          const SizedBox(height: 8),
          Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
            Text('${tir.round()}%',
                style: const TextStyle(
                    color: AppColors.glucoseInRange,
                    fontWeight: FontWeight.w700,
                    fontSize: 18)),
            Text('Target: >70%',
                style: TextStyle(color: context.textMut, fontSize: 10)),
          ]),
        ],
      ),
    );
  }
}

class _TirBar extends StatelessWidget {
  const _TirBar({required this.tir});

  final double tir;

  @override
  Widget build(BuildContext context) {
    const low = 0.05;
    const vlow = 0.01;
    final inRange = tir / 100;
    final high = 1 - inRange - low - vlow;

    return ClipRRect(
      borderRadius: BorderRadius.circular(6),
      child: SizedBox(
        height: 10,
        child: Row(children: [
          Expanded(
              flex: (vlow * 100).round(),
              child: Container(color: AppColors.glucoseVeryLow)),
          Expanded(
              flex: (low * 100).round(),
              child: Container(color: AppColors.glucoseLow)),
          Expanded(
              flex: (inRange * 100).round(),
              child: Container(color: AppColors.glucoseInRange)),
          Expanded(
              flex: ((high * 0.7) * 100).round(),
              child: Container(color: AppColors.glucoseHigh)),
          Expanded(
              flex: ((high * 0.3) * 100).round(),
              child: Container(color: AppColors.glucoseVeryHigh)),
        ]),
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────

class _QuickActions extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final actions = [
      _QuickAction(
        label: 'Bolus',
        icon: Icons.vaccines_rounded,
        color: AppColors.accentPurple,
        route: RouteNames.bolus,
      ),
      _QuickAction(
        label: 'Basal',
        icon: Icons.schedule_rounded,
        color: AppColors.accentCyan,
        route: RouteNames.basal,
      ),
    ];

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Quick Actions',
          style: TextStyle(
            color: context.textPri,
            fontSize: 15,
            fontWeight: FontWeight.w600,
          ),
        ),
        const SizedBox(height: 12),
        Row(
          children: actions
              .map((a) => Expanded(
                    child: Padding(
                      padding: EdgeInsets.only(
                        right: a == actions.last ? 0 : 10,
                      ),
                      child: GestureDetector(
                        onTap: () => context.push(a.route),
                        child: Container(
                          padding: const EdgeInsets.symmetric(vertical: 14),
                          decoration: BoxDecoration(
                            color: a.color.withOpacity(0.08),
                            borderRadius: BorderRadius.circular(16),
                            border:
                                Border.all(color: a.color.withOpacity(0.2)),
                          ),
                          child: Column(
                            children: [
                              Icon(a.icon, color: a.color, size: 22),
                              const SizedBox(height: 6),
                              Text(
                                a.label,
                                style: TextStyle(
                                  color: a.color,
                                  fontSize: 11,
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                    ),
                  ))
              .toList(),
        ),
      ],
    );
  }
}

class _QuickAction {
  const _QuickAction({
    required this.label,
    required this.icon,
    required this.color,
    required this.route,
  });

  final String label;
  final IconData icon;
  final Color color;
  final String route;
}

// ─────────────────────────────────────────────────────────────────────────────

class _DailySummary extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.cardPadding),
      decoration: BoxDecoration(
        color: context.cardBg,
        borderRadius: BorderRadius.circular(AppSpacing.radiusXl),
        border: Border.all(color: context.borderC),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            Text(
              "Today's Summary",
              style: TextStyle(
                color: context.textPri,
                fontWeight: FontWeight.w600,
                fontSize: 15,
              ),
            ),
            const Spacer(),
            Text(
              _today(),
              style: TextStyle(
                color: context.textMut,
                fontSize: 12,
              ),
            ),
          ]),
          const SizedBox(height: 16),
          _SummaryRow(
              label: 'Average Glucose',
              value: '138 mg/dL',
              icon: Icons.show_chart_rounded),
          const SizedBox(height: 10),
          _SummaryRow(
              label: 'Total Insulin',
              value: '28.4 U',
              icon: Icons.water_drop_rounded),
          const SizedBox(height: 10),
          _SummaryRow(
              label: 'Total Carbs',
              value: '145 g',
              icon: Icons.grain_rounded),
          const SizedBox(height: 10),
          _SummaryRow(
              label: 'Alerts Today',
              value: '2 (1 hypo)',
              icon: Icons.notifications_rounded,
              warning: true),
        ],
      ),
    );
  }

  String _today() {
    final now = DateTime.now();
    const months = [
      'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
      'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
    ];
    return '${months[now.month - 1]} ${now.day}';
  }
}

class _SummaryRow extends StatelessWidget {
  const _SummaryRow({
    required this.label,
    required this.value,
    required this.icon,
    this.warning = false,
  });

  final String label;
  final String value;
  final IconData icon;
  final bool warning;

  @override
  Widget build(BuildContext context) {
    final iconColor = warning ? AppColors.warning : context.textMut;
    return Row(
      children: [
        Icon(icon, color: iconColor, size: 16),
        const SizedBox(width: 8),
        Text(
          label,
          style: TextStyle(
            color: context.textSec,
            fontSize: 13,
          ),
        ),
        const Spacer(),
        Text(
          value,
          style: TextStyle(
            color: warning ? AppColors.warning : context.textPri,
            fontSize: 13,
            fontWeight: FontWeight.w600,
          ),
        ),
      ],
    );
  }
}
