import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import '../../../core/constants/app_colors.dart';
import '../../../core/constants/app_spacing.dart';
import '../../../core/utils/theme_ext.dart';
import '../../../data/mock/mock_glucose.dart';
import '../../../data/models/insulin_model.dart';

class BasalScheduleScreen extends StatefulWidget {
  const BasalScheduleScreen({super.key});

  @override
  State<BasalScheduleScreen> createState() => _BasalScheduleScreenState();
}

class _BasalScheduleScreenState extends State<BasalScheduleScreen> {
  bool _editMode = false;
  late final List<BasalSegment> _schedule;

  @override
  void initState() {
    super.initState();
    _schedule = List.from(mockBasalSchedule);
  }

  double get _totalDailyBasal =>
      _schedule.fold(0.0, (sum, s) => sum + s.rate);

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: context.appBg,
      appBar: AppBar(
        backgroundColor: context.appBg,
        title: Text(
          'Basal Schedule',
          style: TextStyle(
            color: context.textPri,
            fontWeight: FontWeight.w700,
          ),
        ),
        actions: [
          TextButton.icon(
            icon: Icon(_editMode ? Icons.save_rounded : Icons.edit_rounded,
                size: 16),
            label: Text(_editMode ? 'Save' : 'Edit'),
            onPressed: () => setState(() => _editMode = !_editMode),
            style: TextButton.styleFrom(foregroundColor: AppColors.primary),
          ),
        ],
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(AppSpacing.screenPadding),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _SummaryCard(totalBasal: _totalDailyBasal)
                .animate()
                .fadeIn(duration: 300.ms),

            const SizedBox(height: 20),

            _BasalTimeline(schedule: _schedule)
                .animate(delay: 100.ms)
                .fadeIn(duration: 400.ms),

            const SizedBox(height: 20),

            Container(
              decoration: BoxDecoration(
                color: context.cardBg,
                borderRadius: BorderRadius.circular(AppSpacing.radiusXl),
                border: Border.all(color: context.borderC),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Padding(
                    padding: const EdgeInsets.all(AppSpacing.cardPadding),
                    child: Row(children: [
                      const Icon(Icons.access_time_rounded,
                          color: AppColors.primary, size: 18),
                      const SizedBox(width: 8),
                      Text(
                        'Hourly Schedule',
                        style: TextStyle(
                          color: context.textPri,
                          fontWeight: FontWeight.w600,
                          fontSize: 14,
                        ),
                      ),
                    ]),
                  ),
                  Divider(height: 1, color: context.divC),
                  ..._schedule.asMap().entries.map(
                        (e) => _ScheduleRow(
                          segment: e.value,
                          index: e.key,
                          editMode: _editMode,
                          onRateChanged: (r) {
                            setState(() {
                              _schedule[e.key] = BasalSegment(
                                hour: e.value.hour,
                                rate: r,
                                aiOptimized: e.value.aiOptimized,
                              );
                            });
                          },
                        )
                            .animate(
                                delay: Duration(milliseconds: e.key * 20))
                            .fadeIn(),
                      ),
                ],
              ),
            ).animate(delay: 200.ms).fadeIn(),
          ],
        ),
      ),
    );
  }
}

class _SummaryCard extends StatelessWidget {
  const _SummaryCard({required this.totalBasal});

  final double totalBasal;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.cardPadding),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: context.isDark
              ? [const Color(0xFF0D1A35), const Color(0xFF0A1220)]
              : [const Color(0xFFEFF6FF), const Color(0xFFF8FAFF)],
        ),
        borderRadius: BorderRadius.circular(AppSpacing.radiusXl),
        border: Border.all(
            color: AppColors.accentCyan.withValues(alpha: 0.25)),
      ),
      child: Row(
        children: [
          Expanded(
              child: _SummaryMetric(
            label: 'Total Daily Basal',
            value: '${totalBasal.toStringAsFixed(1)} U',
            color: AppColors.accentCyan,
          )),
          Expanded(
              child: _SummaryMetric(
            label: 'Avg Rate',
            value: '${(totalBasal / 24).toStringAsFixed(2)} U/h',
            color: AppColors.accentGreen,
          )),
        ],
      ),
    );
  }
}

class _SummaryMetric extends StatelessWidget {
  const _SummaryMetric({
    required this.label,
    required this.value,
    required this.color,
  });

  final String label;
  final String value;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Text(
          value,
          style: TextStyle(
            color: color,
            fontSize: 15,
            fontWeight: FontWeight.w700,
          ),
        ),
        const SizedBox(height: 2),
        Text(
          label,
          style: TextStyle(color: context.textMut, fontSize: 10),
          textAlign: TextAlign.center,
        ),
      ],
    );
  }
}

class _BasalTimeline extends StatelessWidget {
  const _BasalTimeline({required this.schedule});

  final List<BasalSegment> schedule;

  @override
  Widget build(BuildContext context) {
    final maxRate =
        schedule.map((s) => s.rate).reduce((a, b) => a > b ? a : b);
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
            const Icon(Icons.bar_chart_rounded,
                color: AppColors.accentCyan, size: 18),
            const SizedBox(width: 8),
            Text(
              '24-Hour Visualization',
              style: TextStyle(
                color: context.textPri,
                fontWeight: FontWeight.w600,
                fontSize: 14,
              ),
            ),
          ]),
          const SizedBox(height: 16),
          SizedBox(
            height: 80,
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: schedule.map((s) {
                final heightPct = s.rate / maxRate;
                return Expanded(
                  child: Padding(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 0.5),
                    child: Container(
                      height: 80 * heightPct,
                      decoration: BoxDecoration(
                        gradient: LinearGradient(
                          begin: Alignment.topCenter,
                          end: Alignment.bottomCenter,
                          colors: s.aiOptimized
                              ? [
                                  AppColors.accentCyan,
                                  AppColors.primary
                                ]
                              : [
                                  AppColors.primary,
                                  AppColors.primaryDark
                                ],
                        ),
                        borderRadius: const BorderRadius.vertical(
                            top: Radius.circular(2)),
                      ),
                    ),
                  ),
                );
              }).toList(),
            ),
          ),
          const SizedBox(height: 6),
          Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text('12 AM',
                    style: TextStyle(
                        color: context.textMut, fontSize: 9)),
                Text('6 AM',
                    style: TextStyle(
                        color: context.textMut, fontSize: 9)),
                Text('12 PM',
                    style: TextStyle(
                        color: context.textMut, fontSize: 9)),
                Text('6 PM',
                    style: TextStyle(
                        color: context.textMut, fontSize: 9)),
                Text('12 AM',
                    style: TextStyle(
                        color: context.textMut, fontSize: 9)),
              ]),
        ],
      ),
    );
  }
}

class _ScheduleRow extends StatefulWidget {
  const _ScheduleRow({
    required this.segment,
    required this.index,
    required this.editMode,
    required this.onRateChanged,
  });

  final BasalSegment segment;
  final int index;
  final bool editMode;
  final ValueChanged<double> onRateChanged;

  @override
  State<_ScheduleRow> createState() => _ScheduleRowState();
}

class _ScheduleRowState extends State<_ScheduleRow> {
  late final TextEditingController _controller;

  @override
  void initState() {
    super.initState();
    _controller = TextEditingController(
        text: widget.segment.rate.toStringAsFixed(2));
  }

  @override
  void didUpdateWidget(_ScheduleRow oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (!widget.editMode && oldWidget.editMode) {
      _controller.text = widget.segment.rate.toStringAsFixed(2);
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _commit(String val) {
    final parsed = double.tryParse(val);
    if (parsed != null) {
      widget.onRateChanged(parsed.clamp(0.1, 3.0));
      _controller.text = parsed.clamp(0.1, 3.0).toStringAsFixed(2);
    } else {
      _controller.text = widget.segment.rate.toStringAsFixed(2);
    }
  }

  String get _timeLabel {
    final h = widget.segment.hour;
    final next = (h + 1) % 24;
    String fmt(int hr) => hr == 0
        ? '12 AM'
        : hr < 12
            ? '$hr AM'
            : hr == 12
                ? '12 PM'
                : '${hr - 12} PM';
    return '${fmt(h)} – ${fmt(next)}';
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      padding:
          const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      decoration: BoxDecoration(
        border: Border(
          bottom: BorderSide(
            color: context.divC,
            width: widget.index == 23 ? 0 : 1,
          ),
        ),
      ),
      child: Row(
        children: [
          Container(
            width: 3,
            height: 32,
            margin: const EdgeInsets.only(right: 12),
            decoration: BoxDecoration(
              color: widget.segment.aiOptimized
                  ? AppColors.accentCyan
                  : AppColors.primary.withValues(alpha: 0.4),
              borderRadius: BorderRadius.circular(2),
            ),
          ),
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                _timeLabel,
                style: TextStyle(
                  color: context.textPri,
                  fontSize: 12,
                  fontWeight: FontWeight.w500,
                ),
              ),
            ],
          ),
          const Spacer(),
          if (widget.editMode)
            SizedBox(
              width: 96,
              height: 38,
              child: TextField(
                controller: _controller,
                keyboardType: const TextInputType.numberWithOptions(
                    decimal: true),
                textAlign: TextAlign.center,
                style: TextStyle(
                  color: context.textPri,
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                ),
                decoration: InputDecoration(
                  suffixText: 'U/h',
                  suffixStyle: TextStyle(
                    color: context.textMut,
                    fontSize: 11,
                  ),
                  contentPadding: const EdgeInsets.symmetric(
                      horizontal: 8, vertical: 8),
                  enabledBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(9),
                    borderSide: const BorderSide(
                        color: AppColors.primary, width: 1.5),
                  ),
                  focusedBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(9),
                    borderSide: const BorderSide(
                        color: AppColors.accentCyan, width: 2),
                  ),
                  filled: true,
                  fillColor:
                      AppColors.primary.withValues(alpha: 0.08),
                ),
                onSubmitted: _commit,
                onTapOutside: (_) => _commit(_controller.text),
              ),
            )
          else
            Row(children: [
              Text(
                '${widget.segment.rate.toStringAsFixed(2)} U/h',
                style: TextStyle(
                  color: context.textPri,
                  fontWeight: FontWeight.w600,
                  fontSize: 13,
                ),
              ),
              const SizedBox(width: 6),
              _RateIndicator(rate: widget.segment.rate),
            ]),
        ],
      ),
    );
  }
}

class _RateIndicator extends StatelessWidget {
  const _RateIndicator({required this.rate});

  final double rate;

  @override
  Widget build(BuildContext context) {
    final bool isHigh = rate >= 1.0;
    return Container(
      width: 8,
      height: 8,
      decoration: BoxDecoration(
        color: isHigh ? AppColors.warning : AppColors.accentGreen,
        shape: BoxShape.circle,
      ),
    );
  }
}
