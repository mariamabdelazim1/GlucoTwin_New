import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../core/constants/app_colors.dart';
import '../../../core/constants/app_spacing.dart';
import '../../../core/utils/theme_ext.dart';
import '../../../data/models/glucose_reading.dart';
import '../../providers/glucose_provider.dart';
import '../../widgets/common/gradient_button.dart';
import '../../widgets/charts/glucose_chart.dart';

class SimulationScreen extends ConsumerStatefulWidget {
  const SimulationScreen({super.key});

  @override
  ConsumerState<SimulationScreen> createState() => _SimulationScreenState();
}

class _SimulationScreenState extends ConsumerState<SimulationScreen> {
  double _mealCarbs = 60;
  double _insulin = 4;
  double _exercise = 30;
  bool _running = false;
  bool _hasResult = false;
  List<GlucoseReading> _simResults = [];
  List<String> _warnings = [];

  void _runSimulation() {
    setState(() {
      _running = true;
      _hasResult = false;
    });
    Future.delayed(const Duration(milliseconds: 2200), () {
      if (!mounted) return;
      final now = DateTime.now();
      final base = 129.0;
      final mealPeak = (_mealCarbs / 10.0) * 12;
      final insulinDrop = _insulin * 35;
      final exerciseDrop = (_exercise / 60.0) * 20;

      final results = List.generate(25, (i) {
        final mins = i * 12;
        double v = base;
        if (mins < 90) v += mealPeak * (mins / 90.0);
        if (mins >= 30) v -= insulinDrop * ((mins - 30) / 120.0).clamp(0, 1);
        if (mins >= 60) v -= exerciseDrop * ((mins - 60) / 120.0).clamp(0, 1);
        return GlucoseReading(
          timestamp: now.add(Duration(minutes: mins)),
          value: v.clamp(50, 350),
          isPredicted: true,
        );
      });

      final maxGlucose =
          results.map((r) => r.value).reduce((a, b) => a > b ? a : b);
      final minGlucose =
          results.map((r) => r.value).reduce((a, b) => a < b ? a : b);
      final warnings = <String>[];
      if (maxGlucose > 250)
        warnings.add(
            '⚠️ Peak glucose ${maxGlucose.round()} mg/dL — consider increasing insulin');
      if (minGlucose < 70)
        warnings.add(
            '🔴 Glucose may drop to ${minGlucose.round()} mg/dL — risk of hypoglycemia');
      if (warnings.isEmpty)
        warnings.add('✅ Simulation looks safe. No major risks detected.');

      setState(() {
        _running = false;
        _hasResult = true;
        _simResults = results;
        _warnings = warnings;
      });
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: context.appBg,
      body: CustomScrollView(
        slivers: [
          SliverAppBar(
            pinned: true,
            backgroundColor: context.appBg,
            title: Text('What-If Simulator',
                style: TextStyle(
                    fontWeight: FontWeight.w700, color: context.textPri)),
          ),
          SliverPadding(
            padding: const EdgeInsets.fromLTRB(
                AppSpacing.screenPadding, 0,
                AppSpacing.screenPadding, 100),
            sliver: SliverList(
              delegate: SliverChildListDelegate([
                // Controls
                _ControlsCard(
                  mealCarbs: _mealCarbs,
                  insulin: _insulin,
                  exercise: _exercise,
                  onMealChanged: (v) => setState(() {
                    _mealCarbs = v;
                    _hasResult = false;
                  }),
                  onInsulinChanged: (v) => setState(() {
                    _insulin = v;
                    _hasResult = false;
                  }),
                  onExerciseChanged: (v) => setState(() {
                    _exercise = v;
                    _hasResult = false;
                  }),
                ).animate(delay: 100.ms).fadeIn(duration: 400.ms),

                const SizedBox(height: 20),

                GradientButton(
                  label: _running ? 'Running Simulation...' : 'Run Simulation',
                  onPressed: _running ? null : _runSimulation,
                  isLoading: _running,
                  enabled: !_running,
                  icon: Icons.science_rounded,
                  gradient: AppColors.purpleGradient,
                ).animate(delay: 200.ms).fadeIn(),

                if (_hasResult) ...[
                  const SizedBox(height: 20),
                  _ResultsSection(
                    results: _simResults,
                    warnings: _warnings,
                  ).animate().fadeIn(duration: 500.ms).slideY(begin: 0.1, end: 0),
                ],
              ]),
            ),
          ),
        ],
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────

class _ControlsCard extends StatelessWidget {
  const _ControlsCard({
    required this.mealCarbs,
    required this.insulin,
    required this.exercise,
    required this.onMealChanged,
    required this.onInsulinChanged,
    required this.onExerciseChanged,
  });

  final double mealCarbs;
  final double insulin;
  final double exercise;
  final ValueChanged<double> onMealChanged;
  final ValueChanged<double> onInsulinChanged;
  final ValueChanged<double> onExerciseChanged;

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
            const Icon(Icons.tune_rounded, color: AppColors.primary, size: 18),
            const SizedBox(width: 8),
            Text(
              'Simulation Parameters',
              style: TextStyle(
                color: context.textPri,
                fontWeight: FontWeight.w600,
                fontSize: 14,
              ),
            ),
          ]),
          const SizedBox(height: 20),

          _SimSlider(
            label: 'Meal Size',
            value: mealCarbs,
            min: 0,
            max: 150,
            unit: 'g carbs',
            color: AppColors.accentAmber,
            icon: Icons.restaurant_rounded,
            onChanged: onMealChanged,
          ),
          const SizedBox(height: 16),
          _SimSlider(
            label: 'Insulin Dose',
            value: insulin,
            min: 0,
            max: 20,
            unit: 'units',
            color: AppColors.accentPurple,
            icon: Icons.vaccines_rounded,
            onChanged: onInsulinChanged,
          ),
          const SizedBox(height: 16),
          _SimSlider(
            label: 'Exercise',
            value: exercise,
            min: 0,
            max: 120,
            unit: 'min',
            color: AppColors.accentGreen,
            icon: Icons.directions_run_rounded,
            onChanged: onExerciseChanged,
          ),
        ],
      ),
    );
  }
}

class _SimSlider extends StatelessWidget {
  const _SimSlider({
    required this.label,
    required this.value,
    required this.min,
    required this.max,
    required this.unit,
    required this.color,
    required this.icon,
    required this.onChanged,
  });

  final String label;
  final double value;
  final double min;
  final double max;
  final String unit;
  final Color color;
  final IconData icon;
  final ValueChanged<double> onChanged;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(children: [
          Icon(icon, color: color, size: 16),
          const SizedBox(width: 6),
          Text(label,
              style: TextStyle(
                  color: context.textSec,
                  fontSize: 13,
                  fontWeight: FontWeight.w500)),
          const Spacer(),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
            decoration: BoxDecoration(
              color: color.withOpacity(0.12),
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: color.withOpacity(0.3)),
            ),
            child: Text(
              '${value.round()} $unit',
              style: TextStyle(
                color: color,
                fontSize: 12,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
        ]),
        SliderTheme(
          data: SliderTheme.of(context).copyWith(
            activeTrackColor: color,
            inactiveTrackColor: context.borderC,
            thumbColor: color,
            overlayColor: color.withOpacity(0.15),
          ),
          child: Slider(
            value: value,
            min: min,
            max: max,
            onChanged: onChanged,
          ),
        ),
      ],
    );
  }
}

class _ResultsSection extends StatelessWidget {
  const _ResultsSection({
    required this.results,
    required this.warnings,
  });

  final List<GlucoseReading> results;
  final List<String> warnings;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Chart
        Container(
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
                const Icon(Icons.show_chart_rounded,
                    color: AppColors.accentCyan, size: 18),
                const SizedBox(width: 8),
                Text(
                  'Simulated Glucose Outcome',
                  style: TextStyle(
                    color: context.textPri,
                    fontWeight: FontWeight.w600,
                    fontSize: 14,
                  ),
                ),
              ]),
              const SizedBox(height: 4),
              Text(
                'Next 5 hours simulation',
                style: TextStyle(color: context.textMut, fontSize: 11),
              ),
              const SizedBox(height: 12),
              GlucoseLineChart(
                history: [results.first],
                predictions: results.skip(1).toList(),
                height: 200,
              ),
            ],
          ),
        ),

        const SizedBox(height: 16),

        // Warnings/insights
        Column(
          children: warnings.map((w) {
            final isWarning = w.startsWith('⚠️');
            final isDanger = w.startsWith('🔴');

            final color = isDanger
                ? AppColors.danger
                : isWarning
                    ? AppColors.warning
                    : AppColors.accentGreen;

            return Container(
              width: double.infinity,
              margin: const EdgeInsets.only(bottom: 10),
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: color.withOpacity(0.08),
                borderRadius: BorderRadius.circular(14),
                border: Border.all(color: color.withOpacity(0.3)),
              ),
              child: Text(
                w,
                style: TextStyle(color: color, fontSize: 13, height: 1.4),
              ),
            );
          }).toList(),
        ),

        // Metrics
        Container(
          padding: const EdgeInsets.all(AppSpacing.cardPadding),
          decoration: BoxDecoration(
            color: context.cardBg,
            borderRadius: BorderRadius.circular(AppSpacing.radiusXl),
            border: Border.all(color: context.borderC),
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceAround,
            children: [
              _SimMetric(
                label: 'Peak Glucose',
                value:
                    '${results.map((r) => r.value).reduce((a, b) => a > b ? a : b).round()} mg/dL',
                color: AppColors.glucoseHigh,
              ),
              Container(width: 1, height: 40, color: context.borderC),
              _SimMetric(
                label: 'Min Glucose',
                value:
                    '${results.map((r) => r.value).reduce((a, b) => a < b ? a : b).round()} mg/dL',
                color: AppColors.glucoseInRange,
              ),
              Container(width: 1, height: 40, color: context.borderC),
              _SimMetric(
                label: 'Est. TIR',
                value:
                    '${(results.where((r) => r.value >= 70 && r.value <= 180).length / results.length * 100).round()}%',
                color: AppColors.primary,
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _SimMetric extends StatelessWidget {
  const _SimMetric({
    required this.label,
    required this.value,
    required this.color,
  });

  final String label;
  final String value;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Column(children: [
      Text(
        value,
        style:
            TextStyle(color: color, fontSize: 14, fontWeight: FontWeight.w700),
      ),
      const SizedBox(height: 2),
      Text(
        label,
        style: TextStyle(color: context.textMut, fontSize: 10),
      ),
    ]);
  }
}
