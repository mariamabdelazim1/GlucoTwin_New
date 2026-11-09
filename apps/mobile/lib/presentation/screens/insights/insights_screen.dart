import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import '../../../core/constants/app_colors.dart';
import '../../../core/constants/app_spacing.dart';
import '../../../core/utils/theme_ext.dart';

class InsightsScreen extends StatefulWidget {
  const InsightsScreen({super.key});

  @override
  State<InsightsScreen> createState() => _InsightsScreenState();
}

class _InsightsScreenState extends State<InsightsScreen> {
  int _periodIndex = 1; // default: 7d
  static const _periods = ['24h', '7d', '14d', '30d', '90d'];

  // ── Mock data keyed by period ───────────────────────────────────────────────

  static const _tirByPeriod = {
    '24h': (inRange: 82.1, high: 12.3, low: 5.6, trend: '+3.7% vs yesterday'),
    '7d':  (inRange: 78.4, high: 17.1, low: 4.5, trend: '+2.1% vs prev week'),
    '14d': (inRange: 76.2, high: 18.5, low: 5.3, trend: '+1.4% vs prev 14d'),
    '30d': (inRange: 74.8, high: 19.2, low: 6.0, trend: '+0.8% vs prev month'),
    '90d': (inRange: 72.1, high: 21.4, low: 6.5, trend: '+4.3% vs prev 90d'),
  };

  static const _barDataByPeriod = <String, Map<String, double>>{
    '24h': {
      '12am': 88, '4am': 72, '8am': 78,
      '12pm': 65, '4pm': 82, '8pm': 90,
    },
    '7d': {
      'Mon': 74, 'Tue': 81, 'Wed': 77,
      'Thu': 69, 'Fri': 83, 'Sat': 79, 'Sun': 82,
    },
    '14d': {
      'W1 Mon': 72, 'W1 Wed': 78, 'W1 Fri': 80,
      'W1 Sun': 75, 'W2 Mon': 74, 'W2 Wed': 79,
      'W2 Fri': 81, 'W2 Sun': 77,
    },
    '30d': {
      'Wk 1': 73, 'Wk 2': 76, 'Wk 3': 78, 'Wk 4': 80,
    },
    '90d': {
      'Jan': 70, 'Feb': 74, 'Mar': 78,
    },
  };

  static const _avgGlucoseByPeriod = {
    '24h': 132, '7d': 138, '14d': 141, '30d': 144, '90d': 149,
  };

  String get _period => _periods[_periodIndex];

  @override
  Widget build(BuildContext context) {
    final period = _period;
    final tir = _tirByPeriod[period]!;
    final bars = _barDataByPeriod[period]!;
    final avgGlucose = _avgGlucoseByPeriod[period]!;

    return Scaffold(
      backgroundColor: context.appBg,
      body: CustomScrollView(
        slivers: [
          SliverAppBar(
            pinned: true,
            backgroundColor: context.appBg,
            title: Text('Insights & Analytics',
                style: TextStyle(
                    fontWeight: FontWeight.w700, color: context.textPri)),
          ),
          SliverPadding(
            padding: const EdgeInsets.fromLTRB(
                AppSpacing.screenPadding, 0,
                AppSpacing.screenPadding, 100),
            sliver: SliverList(
              delegate: SliverChildListDelegate([
                // Period selector
                _PeriodSelector(
                  selectedIndex: _periodIndex,
                  periods: _periods,
                  onChanged: (i) => setState(() => _periodIndex = i),
                ).animate().fadeIn(duration: 300.ms),
                const SizedBox(height: 20),

                // Daily/period TIR bar chart
                _TirBarCard(period: period, bars: bars)
                    .animate(delay: 100.ms)
                    .fadeIn(duration: 400.ms),
                const SizedBox(height: 16),

                // Glucose distribution + avg
                _GlucoseDistributionCard(
                  period: period,
                  inRange: tir.inRange,
                  high: tir.high,
                  low: tir.low,
                  trend: tir.trend,
                  avgGlucose: avgGlucose,
                ).animate(delay: 200.ms).fadeIn(duration: 400.ms),
                const SizedBox(height: 16),

                // Insights cards
                _InsightsSection(period: period)
                    .animate(delay: 300.ms)
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

class _PeriodSelector extends StatelessWidget {
  const _PeriodSelector({
    required this.selectedIndex,
    required this.periods,
    required this.onChanged,
  });

  final int selectedIndex;
  final List<String> periods;
  final ValueChanged<int> onChanged;

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: Row(
        children: periods.asMap().entries.map((e) {
          final isSelected = e.key == selectedIndex;
          return GestureDetector(
            onTap: () => onChanged(e.key),
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 200),
              margin: const EdgeInsets.only(right: 8),
              padding:
                  const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              decoration: BoxDecoration(
                color: isSelected ? AppColors.primary : context.cardBg,
                borderRadius: BorderRadius.circular(100),
                border: Border.all(
                  color: isSelected ? AppColors.primary : context.borderC,
                ),
              ),
              child: Text(
                e.value,
                style: TextStyle(
                  color: isSelected ? Colors.white : context.textSec,
                  fontSize: 13,
                  fontWeight:
                      isSelected ? FontWeight.w600 : FontWeight.w400,
                ),
              ),
            ),
          );
        }).toList(),
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────

class _TirBarCard extends StatelessWidget {
  const _TirBarCard({required this.period, required this.bars});

  final String period;
  final Map<String, double> bars;

  String get _title {
    return switch (period) {
      '24h' => 'Hourly Time in Range',
      '7d'  => 'Daily Time in Range',
      '14d' => 'Bi-Weekly Time in Range',
      '30d' => 'Weekly Time in Range',
      '90d' => '3-Month Time in Range',
      _     => 'Time in Range',
    };
  }

  @override
  Widget build(BuildContext context) {
    final entries = bars.entries.toList();
    return AnimatedSwitcher(
      duration: const Duration(milliseconds: 400),
      child: Container(
        key: ValueKey(period),
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
              const Icon(Icons.bar_chart_rounded,
                  color: AppColors.primary, size: 18),
              const SizedBox(width: 8),
              Text(
                _title,
                style: TextStyle(
                  color: context.textPri,
                  fontWeight: FontWeight.w600,
                  fontSize: 14,
                ),
              ),
            ]),
            const SizedBox(height: 16),
            SizedBox(
              height: 140,
              child: BarChart(
                BarChartData(
                  barTouchData: BarTouchData(
                    touchTooltipData: BarTouchTooltipData(
                      getTooltipColor: (_) => AppColors.darkCardElevated,
                      getTooltipItem: (group, _, rod, __) =>
                          BarTooltipItem(
                        '${entries[group.x.toInt()].key}\n',
                        const TextStyle(
                            color: AppColors.textSecondaryDark,
                            fontSize: 10),
                        children: [
                          TextSpan(
                            text:
                                '${entries[group.x.toInt()].value.round()}%',
                            style: const TextStyle(
                                color: AppColors.accentGreen,
                                fontWeight: FontWeight.bold),
                          ),
                        ],
                      ),
                    ),
                  ),
                  titlesData: FlTitlesData(
                    bottomTitles: AxisTitles(
                      sideTitles: SideTitles(
                        showTitles: true,
                        getTitlesWidget: (val, _) => Padding(
                          padding: const EdgeInsets.only(top: 4),
                          child: Text(
                            entries[val.toInt()].key,
                            style: TextStyle(
                              color: context.textMut,
                              fontSize: 9,
                            ),
                          ),
                        ),
                      ),
                    ),
                    leftTitles: AxisTitles(
                      sideTitles: SideTitles(
                        showTitles: true,
                        interval: 25,
                        reservedSize: 30,
                        getTitlesWidget: (val, _) => Text(
                          '${val.round()}',
                          style: TextStyle(
                            color: context.textMut,
                            fontSize: 9,
                          ),
                        ),
                      ),
                    ),
                    rightTitles: const AxisTitles(
                        sideTitles: SideTitles(showTitles: false)),
                    topTitles: const AxisTitles(
                        sideTitles: SideTitles(showTitles: false)),
                  ),
                  gridData: FlGridData(
                    show: true,
                    drawVerticalLine: false,
                    horizontalInterval: 25,
                    getDrawingHorizontalLine: (_) => FlLine(
                      color: context.borderC.withOpacity(0.5),
                      strokeWidth: 1,
                      dashArray: [4, 4],
                    ),
                  ),
                  borderData: FlBorderData(show: false),
                  maxY: 100,
                  barGroups: entries.asMap().entries.map((e) {
                    final value = e.value.value;
                    return BarChartGroupData(
                      x: e.key,
                      barRods: [
                        BarChartRodData(
                          toY: value,
                          gradient: LinearGradient(
                            begin: Alignment.bottomCenter,
                            end: Alignment.topCenter,
                            colors: value >= 70
                                ? [
                                    AppColors.accentGreen,
                                    AppColors.accentGreen.withOpacity(0.7)
                                  ]
                                : [
                                    AppColors.warning,
                                    AppColors.warning.withOpacity(0.7)
                                  ],
                          ),
                          width: entries.length > 5 ? 16 : 22,
                          borderRadius: const BorderRadius.vertical(
                              top: Radius.circular(6)),
                          backDrawRodData: BackgroundBarChartRodData(
                            show: true,
                            toY: 100,
                            color: context.borderC.withOpacity(0.3),
                          ),
                        ),
                      ],
                    );
                  }).toList(),
                ),
                duration: const Duration(milliseconds: 400),
                curve: Curves.easeOutCubic,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────

class _GlucoseDistributionCard extends StatelessWidget {
  const _GlucoseDistributionCard({
    required this.period,
    required this.inRange,
    required this.high,
    required this.low,
    required this.trend,
    required this.avgGlucose,
  });

  final String period;
  final double inRange;
  final double high;
  final double low;
  final String trend;
  final int avgGlucose;

  @override
  Widget build(BuildContext context) {
    return AnimatedSwitcher(
      duration: const Duration(milliseconds: 350),
      child: Container(
        key: ValueKey('dist_$period'),
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
              const Icon(Icons.pie_chart_rounded,
                  color: AppColors.accentPurple, size: 18),
              const SizedBox(width: 8),
              Text(
                'Glucose Distribution',
                style: TextStyle(
                  color: context.textPri,
                  fontWeight: FontWeight.w600,
                  fontSize: 14,
                ),
              ),
              const Spacer(),
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                decoration: BoxDecoration(
                  color: AppColors.primary.withOpacity(0.1),
                  borderRadius: BorderRadius.circular(100),
                ),
                child: Text(
                  period,
                  style: const TextStyle(
                    color: AppColors.primary,
                    fontSize: 11,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
            ]),
            const SizedBox(height: 16),
            Row(children: [
              SizedBox(
                width: 120,
                height: 120,
                child: PieChart(
                  PieChartData(
                    sections: [
                      PieChartSectionData(
                        value: inRange,
                        color: AppColors.glucoseInRange,
                        radius: 38,
                        showTitle: false,
                      ),
                      PieChartSectionData(
                        value: high,
                        color: AppColors.glucoseHigh,
                        radius: 34,
                        showTitle: false,
                      ),
                      PieChartSectionData(
                        value: low,
                        color: AppColors.glucoseLow,
                        radius: 30,
                        showTitle: false,
                      ),
                    ],
                    centerSpaceRadius: 28,
                    sectionsSpace: 2,
                  ),
                ),
              ),
              const SizedBox(width: 20),
              Expanded(
                child: Column(children: [
                  _Legend('In Range (70–180)', inRange,
                      AppColors.glucoseInRange),
                  const SizedBox(height: 8),
                  _Legend('High (>180)', high, AppColors.glucoseHigh),
                  const SizedBox(height: 8),
                  _Legend('Low (<70)', low, AppColors.glucoseLow),
                  const SizedBox(height: 12),
                  Row(children: [
                    Icon(Icons.monitor_heart_rounded,
                        color: context.textMut, size: 13),
                    const SizedBox(width: 4),
                    Text(
                      'Avg: $avgGlucose mg/dL',
                      style: TextStyle(
                          color: context.textSec,
                          fontSize: 11,
                          fontWeight: FontWeight.w500),
                    ),
                  ]),
                ]),
              ),
            ]),
            const SizedBox(height: 12),
            Row(children: [
              const Icon(Icons.trending_up_rounded,
                  color: AppColors.accentGreen, size: 14),
              const SizedBox(width: 4),
              Text(
                trend,
                style: const TextStyle(
                    color: AppColors.accentGreen, fontSize: 12),
              ),
            ]),
          ],
        ),
      ),
    );
  }
}

class _Legend extends StatelessWidget {
  const _Legend(this.label, this.value, this.color);

  final String label;
  final double value;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Row(children: [
      Container(
        width: 10,
        height: 10,
        decoration: BoxDecoration(color: color, shape: BoxShape.circle),
      ),
      const SizedBox(width: 6),
      Expanded(
        child: Text(
          label,
          style: TextStyle(color: context.textSec, fontSize: 11),
        ),
      ),
      Text(
        '${value.round()}%',
        style:
            TextStyle(color: color, fontSize: 12, fontWeight: FontWeight.w600),
      ),
    ]);
  }
}

// ─────────────────────────────────────────────────────────────────────────────

class _InsightsSection extends StatelessWidget {
  const _InsightsSection({required this.period});

  final String period;

  @override
  Widget build(BuildContext context) {
    final insights = [
      _InsightData(
        icon: Icons.nightlight_round_rounded,
        title: 'Dawn Phenomenon Detected',
        body:
            'Glucose rises 18–22 mg/dL between 4–7 AM. Consider a basal increase of +0.15 U/h.',
        color: AppColors.accentPurple,
      ),
      _InsightData(
        icon: Icons.directions_run_rounded,
        title: 'Exercise Sensitivity',
        body:
            'Post-exercise glucose drops 30–45 mg/dL on average. Reduce correction boluses after activity.',
        color: AppColors.accentGreen,
      ),
      _InsightData(
        icon: Icons.restaurant_rounded,
        title: 'Lunch Spikes',
        body:
            'Tuesday and Thursday lunches cause the highest spikes (+68 mg/dL avg). Consider a 20-min pre-bolus.',
        color: AppColors.accentAmber,
      ),
    ];

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(children: [
          const Icon(Icons.lightbulb_outline_rounded,
              color: AppColors.primary, size: 16),
          const SizedBox(width: 6),
          Text(
            'Insights · $period',
            style: TextStyle(
              color: context.textPri,
              fontWeight: FontWeight.w600,
              fontSize: 15,
            ),
          ),
        ]),
        const SizedBox(height: 12),
        ...insights.map((i) => Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: _InsightCard(insight: i),
            )),
      ],
    );
  }
}

class _InsightData {
  const _InsightData({
    required this.icon,
    required this.title,
    required this.body,
    required this.color,
  });

  final IconData icon;
  final String title;
  final String body;
  final Color color;
}

class _InsightCard extends StatelessWidget {
  const _InsightCard({required this.insight});

  final _InsightData insight;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: insight.color.withOpacity(0.05),
        borderRadius: BorderRadius.circular(AppSpacing.radiusXl),
        border: Border.all(color: insight.color.withOpacity(0.2)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 38,
            height: 38,
            decoration: BoxDecoration(
              color: insight.color.withOpacity(0.12),
              borderRadius: BorderRadius.circular(10),
            ),
            child: Icon(insight.icon, color: insight.color, size: 18),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  insight.title,
                  style: TextStyle(
                    color: context.textPri,
                    fontWeight: FontWeight.w600,
                    fontSize: 13,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  insight.body,
                  style: TextStyle(
                    color: context.textSec,
                    fontSize: 12,
                    height: 1.4,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
