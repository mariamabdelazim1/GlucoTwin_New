import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import '../../../core/constants/app_colors.dart';
import '../../../core/utils/theme_ext.dart';
import '../../../data/models/glucose_reading.dart';
import '../../../core/utils/glucose_utils.dart';

class GlucoseLineChart extends StatelessWidget {
  const GlucoseLineChart({
    super.key,
    required this.history,
    required this.predictions,
    this.height = 200,
    this.showAxes = true,
    this.showRangeZone = true,
  });

  final List<GlucoseReading> history;
  final List<GlucoseReading> predictions;
  final double height;
  final bool showAxes;
  final bool showRangeZone;

  @override
  Widget build(BuildContext context) {
    if (history.isEmpty) return SizedBox(height: height);

    final allReadings = [...history, ...predictions];
    final startTime = history.first.timestamp.millisecondsSinceEpoch.toDouble();

    List<FlSpot> historicSpots = history
        .map((r) => FlSpot(
              (r.timestamp.millisecondsSinceEpoch - startTime) / 60000,
              r.value,
            ))
        .toList();

    List<FlSpot> predictionSpots = predictions
        .map((r) => FlSpot(
              (r.timestamp.millisecondsSinceEpoch - startTime) / 60000,
              r.value,
            ))
        .toList();

    // Connect history and predictions
    if (history.isNotEmpty && predictions.isNotEmpty) {
      predictionSpots.insert(0, historicSpots.last);
    }

    // Find highest and lowest spots in historic data for dot markers
    final historicMax = historicSpots.reduce((a, b) => a.y > b.y ? a : b);
    final historicMin = historicSpots.reduce((a, b) => a.y < b.y ? a : b);

    // Find highest and lowest in prediction data (excluding the bridging first spot)
    final actualPredSpots = predictionSpots.length > 1
        ? predictionSpots.sublist(1)
        : predictionSpots;
    final predMax = actualPredSpots.isNotEmpty
        ? actualPredSpots.reduce((a, b) => a.y > b.y ? a : b)
        : null;
    final predMin = actualPredSpots.isNotEmpty
        ? actualPredSpots.reduce((a, b) => a.y < b.y ? a : b)
        : null;

    final minY = (allReadings.map((e) => e.value).reduce((a, b) => a < b ? a : b) - 20)
        .clamp(40.0, 60.0);
    final maxY = (allReadings.map((e) => e.value).reduce((a, b) => a > b ? a : b) + 20)
        .clamp(200.0, 320.0);

    final gridColor = context.borderC.withValues(alpha: 0.5);
    final axisLabelColor = context.textMut;
    final tooltipBg = context.isDark ? AppColors.darkCardElevated : Colors.white;

    return SizedBox(
      height: height,
      child: LineChart(
        LineChartData(
          minX: 0,
          maxX: (predictionSpots.isNotEmpty ? predictionSpots.last.x : historicSpots.last.x) + 5,
          minY: minY,
          maxY: maxY,
          clipData: const FlClipData.all(),
          backgroundColor: Colors.transparent,
          gridData: FlGridData(
            show: showAxes,
            drawHorizontalLine: true,
            drawVerticalLine: false,
            horizontalInterval: 50,
            getDrawingHorizontalLine: (value) => FlLine(
              color: gridColor,
              strokeWidth: 1,
              dashArray: [4, 4],
            ),
          ),
          borderData: FlBorderData(show: false),
          titlesData: FlTitlesData(
            leftTitles: AxisTitles(
              sideTitles: SideTitles(
                showTitles: showAxes,
                interval: 50,
                reservedSize: 38,
                getTitlesWidget: (value, _) => Text(
                  value.toInt().toString(),
                  style: TextStyle(
                    color: axisLabelColor,
                    fontSize: 10,
                  ),
                ),
              ),
            ),
            rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
            topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
            bottomTitles: AxisTitles(
              sideTitles: SideTitles(
                showTitles: showAxes,
                interval: 60,
                reservedSize: 22,
                getTitlesWidget: (value, _) {
                  final mins = value.toInt();
                  if (mins < 0) return const SizedBox();
                  final label = mins < 180
                      ? '-${(180 - mins)}m'
                      : '+${mins - 180}m';
                  return Text(
                    label,
                    style: TextStyle(
                      color: axisLabelColor,
                      fontSize: 9,
                    ),
                  );
                },
              ),
            ),
          ),
          extraLinesData: showRangeZone
              ? ExtraLinesData(
                  horizontalLines: [
                    HorizontalLine(
                      y: 70,
                      color: AppColors.glucoseInRange.withValues(alpha: 0.3),
                      strokeWidth: 1,
                      dashArray: [6, 3],
                      label: HorizontalLineLabel(
                        show: true,
                        labelResolver: (_) => '70',
                        style: const TextStyle(
                          color: AppColors.glucoseInRange,
                          fontSize: 9,
                        ),
                        alignment: Alignment.topRight,
                      ),
                    ),
                    HorizontalLine(
                      y: 180,
                      color: AppColors.glucoseInRange.withValues(alpha: 0.3),
                      strokeWidth: 1,
                      dashArray: [6, 3],
                      label: HorizontalLineLabel(
                        show: true,
                        labelResolver: (_) => '180',
                        style: const TextStyle(
                          color: AppColors.glucoseInRange,
                          fontSize: 9,
                        ),
                        alignment: Alignment.bottomRight,
                      ),
                    ),
                  ],
                )
              : const ExtraLinesData(),
          rangeAnnotations: showRangeZone
              ? RangeAnnotations(
                  horizontalRangeAnnotations: [
                    HorizontalRangeAnnotation(
                      y1: 70,
                      y2: 180,
                      color: AppColors.glucoseInRange.withValues(alpha: 0.05),
                    ),
                  ],
                )
              : const RangeAnnotations(),
          lineBarsData: [
            // Historic line
            LineChartBarData(
              spots: historicSpots,
              isCurved: true,
              curveSmoothness: 0.35,
              color: AppColors.primary,
              barWidth: 2.5,
              isStrokeCapRound: true,
              dotData: FlDotData(
                show: true,
                checkToShowDot: (spot, _) =>
                    spot == historicMax || spot == historicMin,
                getDotPainter: (spot, percent, bar, index) =>
                    FlDotCirclePainter(
                  radius: 5,
                  color: AppColors.primary,
                  strokeWidth: 2,
                  strokeColor: Colors.white,
                ),
              ),
              belowBarData: BarAreaData(
                show: true,
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [
                    AppColors.primary.withValues(alpha: 0.20),
                    AppColors.primary.withValues(alpha: 0.0),
                  ],
                ),
              ),
            ),
            // Prediction line (dashed)
            LineChartBarData(
              spots: predictionSpots,
              isCurved: true,
              curveSmoothness: 0.35,
              color: AppColors.accentCyan.withValues(alpha: 0.8),
              barWidth: 2,
              isStrokeCapRound: true,
              dashArray: [6, 4],
              dotData: FlDotData(
                show: true,
                checkToShowDot: (spot, _) =>
                    spot != predictionSpots.first &&
                    (spot == predMax || spot == predMin),
                getDotPainter: (spot, percent, bar, index) =>
                    FlDotCirclePainter(
                  radius: 4,
                  color: AppColors.accentCyan,
                  strokeWidth: 1.5,
                  strokeColor: Colors.white,
                ),
              ),
              belowBarData: BarAreaData(
                show: true,
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [
                    AppColors.accentCyan.withValues(alpha: 0.10),
                    AppColors.accentCyan.withValues(alpha: 0.0),
                  ],
                ),
              ),
            ),
          ],
          lineTouchData: LineTouchData(
            enabled: true,
            touchTooltipData: LineTouchTooltipData(
              getTooltipColor: (_) => tooltipBg,
              tooltipRoundedRadius: 10,
              getTooltipItems: (spots) => spots
                  .map(
                    (s) => LineTooltipItem(
                      '${s.y.round()} mg/dL',
                      TextStyle(
                        color: GlucoseUtils.getColor(s.y),
                        fontWeight: FontWeight.w600,
                        fontSize: 12,
                      ),
                    ),
                  )
                  .toList(),
            ),
          ),
        ),
        duration: const Duration(milliseconds: 800),
        curve: Curves.easeOutCubic,
      ),
    );
  }
}
