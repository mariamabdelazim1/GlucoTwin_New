import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:go_router/go_router.dart';
import '../../../core/constants/app_colors.dart';
import '../../../core/constants/app_spacing.dart';
import '../../../core/utils/theme_ext.dart';
import '../../widgets/common/gradient_button.dart';
import '../../widgets/charts/glucose_chart.dart';
import '../../../data/models/glucose_reading.dart';

class BolusScreen extends StatefulWidget {
  const BolusScreen({super.key});

  @override
  State<BolusScreen> createState() => _BolusScreenState();
}

class _BolusScreenState extends State<BolusScreen> {
  double _carbs = 45;
  final double _currentGlucose = 129;
  String? _mealType;
  bool _calculated = false;
  bool _calculating = false;
  final _foodDescController = TextEditingController();

  @override
  void dispose() {
    _foodDescController.dispose();
    super.dispose();
  }

  void _calculate() {
    setState(() => _calculating = true);
    Future.delayed(const Duration(milliseconds: 1600), () {
      if (mounted) {
        setState(() {
          _calculating = false;
          _calculated = true;
        });
      }
    });
  }

  double get _suggestedBolus {
    final mealUnits = _carbs / 12.0;
    final correctionUnits = (_currentGlucose - 100) / 42.0;
    return (mealUnits + correctionUnits).clamp(0.0, 20.0);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: context.appBg,
      appBar: AppBar(
        backgroundColor: context.appBg,
        title: Text(
          'Bolus Predictions',
          style: TextStyle(
              color: context.textPri, fontWeight: FontWeight.w700),
        ),
        leading: IconButton(
          icon: const Icon(Icons.keyboard_arrow_down_rounded, size: 28),
          onPressed: () => context.pop(),
        ),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(AppSpacing.screenPadding),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _InputSection(
              carbs: _carbs,
              selectedMeal: _mealType,
              foodDescController: _foodDescController,
              onCarbsChanged: (v) => setState(() => _carbs = v),
              onMealSelected: (m) => setState(() => _mealType = m),
            ).animate().fadeIn(duration: 300.ms).slideY(begin: 0.1, end: 0),

            const SizedBox(height: 20),

            // Always-visible: log without needing a prediction first
            const _QuickBolusLog()
                .animate(delay: 150.ms)
                .fadeIn(duration: 300.ms),

            const SizedBox(height: 20),

            if (!_calculated)
              GradientButton(
                label: 'Calculate Bolus',
                onPressed: _carbs > 0 ? _calculate : null,
                enabled: _carbs > 0,
                isLoading: _calculating,
                icon: Icons.calculate_rounded,
              ).animate(delay: 200.ms).fadeIn()
            else
              _ResultSection(
                suggestedBolus: _suggestedBolus,
                carbs: _carbs,
                glucose: _currentGlucose,
              ).animate().fadeIn(duration: 500.ms).scale(
                  begin: const Offset(0.95, 0.95),
                  end: const Offset(1.0, 1.0)),
          ],
        ),
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────

class _InputSection extends StatelessWidget {
  const _InputSection({
    required this.carbs,
    required this.selectedMeal,
    required this.foodDescController,
    required this.onCarbsChanged,
    required this.onMealSelected,
  });

  final double carbs;
  final String? selectedMeal;
  final TextEditingController foodDescController;
  final ValueChanged<double> onCarbsChanged;
  final ValueChanged<String> onMealSelected;

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
          Text(
            'Meal Details',
            style: TextStyle(
              color: context.textPri,
              fontWeight: FontWeight.w600,
              fontSize: 16,
            ),
          ),
          const SizedBox(height: 16),

          Text('Meal Type',
              style: TextStyle(
                  color: context.textSec, fontSize: 12)),
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children:
                ['Breakfast', 'Lunch', 'Dinner', 'Snack'].map((m) {
              final isSelected = m == selectedMeal;
              return GestureDetector(
                onTap: () => onMealSelected(m),
                child: AnimatedContainer(
                  duration: const Duration(milliseconds: 200),
                  padding: const EdgeInsets.symmetric(
                      horizontal: 14, vertical: 8),
                  decoration: BoxDecoration(
                    color: isSelected
                        ? AppColors.primary.withValues(alpha: 0.15)
                        : context.cardBgEl,
                    borderRadius: BorderRadius.circular(100),
                    border: Border.all(
                      color: isSelected
                          ? AppColors.primary.withValues(alpha: 0.6)
                          : context.borderC,
                    ),
                  ),
                  child: Text(
                    m,
                    style: TextStyle(
                      color: isSelected
                          ? AppColors.primary
                          : context.textSec,
                      fontSize: 13,
                      fontWeight: isSelected
                          ? FontWeight.w600
                          : FontWeight.w400,
                    ),
                  ),
                ),
              );
            }).toList(),
          ),

          const SizedBox(height: 16),

          Text('Food Description',
              style: TextStyle(
                  color: context.textSec, fontSize: 12)),
          const SizedBox(height: 8),
          TextField(
            controller: foodDescController,
            style: TextStyle(color: context.textPri, fontSize: 14),
            decoration: InputDecoration(
              hintText: 'e.g. Rice with chicken, apple juice…',
              hintStyle: TextStyle(
                color: context.textMut.withValues(alpha: 0.7),
                fontSize: 13,
              ),
              prefixIcon: Icon(Icons.restaurant_menu_rounded,
                  color: context.textMut, size: 18),
              contentPadding: const EdgeInsets.symmetric(
                  horizontal: 16, vertical: 12),
              filled: true,
              fillColor: context.cardBgEl,
              enabledBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
                borderSide: BorderSide(color: context.borderC),
              ),
              focusedBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
                borderSide: const BorderSide(
                    color: AppColors.primary, width: 1.5),
              ),
            ),
          ),

          const SizedBox(height: 20),

          Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text('Carbohydrates',
                    style: TextStyle(
                        color: context.textSec, fontSize: 12)),
                Container(
                  padding: const EdgeInsets.symmetric(
                      horizontal: 10, vertical: 4),
                  decoration: BoxDecoration(
                    gradient: const LinearGradient(
                        colors: AppColors.primaryGradient),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Text(
                    '${carbs.round()} g',
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 14,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
              ]),
          Slider(
            value: carbs,
            min: 0,
            max: 150,
            divisions: 150,
            onChanged: onCarbsChanged,
          ),
        ],
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────

class _ResultSection extends StatefulWidget {
  const _ResultSection({
    required this.suggestedBolus,
    required this.carbs,
    required this.glucose,
  });

  final double suggestedBolus;
  final double carbs;
  final double glucose;

  @override
  State<_ResultSection> createState() => _ResultSectionState();
}

class _ResultSectionState extends State<_ResultSection> {
  bool _editingBolus = false;
  double? _customBolus;
  late final TextEditingController _editController;

  double get _displayedBolus => _customBolus ?? widget.suggestedBolus;

  @override
  void initState() {
    super.initState();
    _editController = TextEditingController(
      text: widget.suggestedBolus.toStringAsFixed(1),
    );
  }

  @override
  void dispose() {
    _editController.dispose();
    super.dispose();
  }

  void _confirmEdit() {
    final parsed = double.tryParse(_editController.text);
    if (parsed != null && parsed > 0) {
      setState(() {
        _customBolus = parsed.clamp(0.0, 20.0);
        _editingBolus = false;
      });
    } else {
      _editController.text = _displayedBolus.toStringAsFixed(1);
      setState(() => _editingBolus = false);
    }
  }

  void _cancelEdit() {
    _editController.text = _displayedBolus.toStringAsFixed(1);
    setState(() => _editingBolus = false);
  }

  @override
  Widget build(BuildContext context) {
    final mealUnits = widget.carbs / 12.0;
    final correctionUnits =
        ((widget.glucose - 100) / 42.0).clamp(0.0, 10.0);
    final now = DateTime.now();
    final predictions = [
      GlucoseReading(
          timestamp: now.add(const Duration(minutes: 30)),
          value: widget.glucose + 30),
      GlucoseReading(
          timestamp: now.add(const Duration(minutes: 60)),
          value: widget.glucose + 45),
      GlucoseReading(
          timestamp: now.add(const Duration(minutes: 90)),
          value: widget.glucose + 20),
      GlucoseReading(
          timestamp: now.add(const Duration(minutes: 120)),
          value: widget.glucose - 10),
    ];

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // ── Main result card ──────────────────────────────────────────
        Container(
          padding: const EdgeInsets.all(AppSpacing.cardPadding),
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              colors: context.isDark
                  ? [
                      const Color(0xFF0D1A35),
                      const Color(0xFF0A1220)
                    ]
                  : [
                      const Color(0xFFEFF6FF),
                      const Color(0xFFF8FAFF)
                    ],
            ),
            borderRadius: BorderRadius.circular(AppSpacing.radiusXl),
            border: Border.all(
                color: AppColors.primary.withValues(alpha: 0.3)),
            boxShadow: [
              BoxShadow(
                color: AppColors.primary.withValues(alpha: 0.12),
                blurRadius: 24,
                offset: const Offset(0, 8),
              ),
            ],
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (_customBolus != null) ...[
                Container(
                  padding: const EdgeInsets.symmetric(
                      horizontal: 8, vertical: 3),
                  decoration: BoxDecoration(
                    color: AppColors.warning.withValues(alpha: 0.12),
                    borderRadius: BorderRadius.circular(100),
                    border: Border.all(
                        color:
                            AppColors.warning.withValues(alpha: 0.3)),
                  ),
                  child: const Text(
                    'Manually edited',
                    style: TextStyle(
                        color: AppColors.warning,
                        fontSize: 10,
                        fontWeight: FontWeight.w600),
                  ),
                ),
                const SizedBox(height: 12),
              ],

              const SizedBox(height: 4),

              Row(
                crossAxisAlignment: CrossAxisAlignment.center,
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'Suggested Bolus',
                          style: TextStyle(
                            color: context.textSec,
                            fontSize: 12,
                            letterSpacing: 0.5,
                          ),
                        ),
                        const SizedBox(height: 4),
                        if (_editingBolus)
                          Row(children: [
                            SizedBox(
                              width: 110,
                              child: TextField(
                                controller: _editController,
                                autofocus: true,
                                keyboardType:
                                    const TextInputType
                                        .numberWithOptions(decimal: true),
                                style: const TextStyle(
                                  color: AppColors.primary,
                                  fontSize: 40,
                                  fontWeight: FontWeight.w800,
                                  height: 1.1,
                                  letterSpacing: -1,
                                ),
                                decoration: InputDecoration(
                                  suffixText: 'U',
                                  suffixStyle: TextStyle(
                                    color: context.textSec,
                                    fontSize: 20,
                                    fontWeight: FontWeight.w600,
                                  ),
                                  contentPadding: EdgeInsets.zero,
                                  border: InputBorder.none,
                                  enabledBorder: InputBorder.none,
                                  focusedBorder:
                                      const UnderlineInputBorder(
                                    borderSide: BorderSide(
                                        color: AppColors.primary,
                                        width: 2),
                                  ),
                                  filled: false,
                                ),
                                onSubmitted: (_) => _confirmEdit(),
                              ),
                            ),
                            const SizedBox(width: 10),
                            GestureDetector(
                              onTap: _confirmEdit,
                              child: Container(
                                width: 34,
                                height: 34,
                                decoration: BoxDecoration(
                                  color: AppColors.accentGreen
                                      .withValues(alpha: 0.15),
                                  borderRadius:
                                      BorderRadius.circular(9),
                                  border: Border.all(
                                      color: AppColors.accentGreen
                                          .withValues(alpha: 0.4)),
                                ),
                                child: const Icon(
                                    Icons.check_rounded,
                                    color: AppColors.accentGreen,
                                    size: 18),
                              ),
                            ),
                            const SizedBox(width: 6),
                            GestureDetector(
                              onTap: _cancelEdit,
                              child: Container(
                                width: 34,
                                height: 34,
                                decoration: BoxDecoration(
                                  color: AppColors.danger
                                      .withValues(alpha: 0.12),
                                  borderRadius:
                                      BorderRadius.circular(9),
                                  border: Border.all(
                                      color: AppColors.danger
                                          .withValues(alpha: 0.3)),
                                ),
                                child: const Icon(
                                    Icons.close_rounded,
                                    color: AppColors.danger,
                                    size: 18),
                              ),
                            ),
                          ])
                        else
                          Row(
                            crossAxisAlignment:
                                CrossAxisAlignment.end,
                            children: [
                              Text(
                                _displayedBolus.toStringAsFixed(1),
                                style: const TextStyle(
                                  color: AppColors.primary,
                                  fontSize: 56,
                                  fontWeight: FontWeight.w800,
                                  height: 1.0,
                                  letterSpacing: -2,
                                ),
                              ),
                              Padding(
                                padding: const EdgeInsets.only(
                                    bottom: 8, left: 4),
                                child: Text(
                                  'U',
                                  style: TextStyle(
                                    color: context.textSec,
                                    fontSize: 22,
                                    fontWeight: FontWeight.w600,
                                  ),
                                ),
                              ),
                              const SizedBox(width: 8),
                              Padding(
                                padding: const EdgeInsets.only(
                                    bottom: 10),
                                child: GestureDetector(
                                  onTap: () {
                                    _editController.text =
                                        _displayedBolus
                                            .toStringAsFixed(1);
                                    setState(
                                        () => _editingBolus = true);
                                  },
                                  child: Container(
                                    width: 30,
                                    height: 30,
                                    decoration: BoxDecoration(
                                      color: AppColors.primary
                                          .withValues(alpha: 0.12),
                                      borderRadius:
                                          BorderRadius.circular(8),
                                      border: Border.all(
                                          color: AppColors.primary
                                              .withValues(alpha: 0.3)),
                                    ),
                                    child: const Icon(
                                        Icons.edit_rounded,
                                        color: AppColors.primary,
                                        size: 14),
                                  ),
                                ),
                              ),
                            ],
                          ),
                      ],
                    ),
                  ),
                  Column(
                    crossAxisAlignment: CrossAxisAlignment.end,
                    children: [
                      _BolusBreakdown(
                          label: 'Meal', value: mealUnits),
                      const SizedBox(height: 6),
                      _BolusBreakdown(
                          label: 'Correction',
                          value: correctionUnits),
                    ],
                  ),
                ],
              ),
            ],
          ),
        ),

        const SizedBox(height: 16),

        // ── Predicted glucose curve ──────────────────────────────────
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
              Text(
                'Predicted Glucose Curve',
                style: TextStyle(
                  color: context.textPri,
                  fontWeight: FontWeight.w600,
                  fontSize: 13,
                ),
              ),
              const SizedBox(height: 2),
              Text(
                'After taking this bolus',
                style: TextStyle(
                    color: context.textMut, fontSize: 11),
              ),
              const SizedBox(height: 12),
              GlucoseLineChart(
                history: [
                  GlucoseReading(
                      timestamp: DateTime.now(),
                      value: widget.glucose)
                ],
                predictions: predictions,
                height: 140,
                showAxes: false,
              ),
            ],
          ),
        ),

        const SizedBox(height: 16),

        GradientButton(
          label: 'Deliver Bolus',
          onPressed: () => context.pop(),
          icon: Icons.vaccines_rounded,
        ),
        const SizedBox(height: 12),
        SizedBox(
          width: double.infinity,
          height: 48,
          child: TextButton(
            onPressed: () => context.pop(),
            child: Text(
              'Cancel',
              style: TextStyle(color: context.textSec),
            ),
          ),
        ),
      ],
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────

class _QuickBolusLog extends StatefulWidget {
  const _QuickBolusLog();

  @override
  State<_QuickBolusLog> createState() => _QuickBolusLogState();
}

class _QuickBolusLogState extends State<_QuickBolusLog> {
  bool _logged = false;
  String _loggedText = '';
  final _ctrl = TextEditingController();

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  void _log() {
    final val = double.tryParse(_ctrl.text);
    if (val != null && val > 0) {
      setState(() {
        _logged = true;
        _loggedText = val.toStringAsFixed(1);
      });
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
              '$_loggedText U bolus logged at ${TimeOfDay.now().format(context)}'),
          backgroundColor: AppColors.accentGreen,
        ),
      );
    }
  }

  void _reset() => setState(() {
        _logged = false;
        _loggedText = '';
        _ctrl.clear();
      });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.cardPadding),
      decoration: BoxDecoration(
        color: context.cardBg,
        borderRadius: BorderRadius.circular(AppSpacing.radiusXl),
        border: Border.all(
          color: _logged
              ? AppColors.accentGreen.withValues(alpha: 0.4)
              : context.borderC,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            Container(
              width: 32,
              height: 32,
              decoration: BoxDecoration(
                color: AppColors.accentGreen.withValues(alpha: 0.12),
                borderRadius: BorderRadius.circular(9),
              ),
              child: const Icon(Icons.edit_note_rounded,
                  color: AppColors.accentGreen, size: 18),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Log Actual Bolus',
                    style: TextStyle(
                      color: context.textPri,
                      fontWeight: FontWeight.w600,
                      fontSize: 14,
                    ),
                  ),
                  Text(
                    'Record units given without a prediction',
                    style:
                        TextStyle(color: context.textMut, fontSize: 11),
                  ),
                ],
              ),
            ),
            if (_logged)
              GestureDetector(
                onTap: _reset,
                child: Icon(Icons.refresh_rounded,
                    color: context.textMut, size: 18),
              ),
          ]),
          const SizedBox(height: 14),
          if (_logged)
            Row(children: [
              const Icon(Icons.check_circle_rounded,
                  color: AppColors.accentGreen, size: 20),
              const SizedBox(width: 8),
              Text(
                '$_loggedText U logged at ${TimeOfDay.now().format(context)}',
                style: const TextStyle(
                  color: AppColors.accentGreen,
                  fontWeight: FontWeight.w600,
                  fontSize: 13,
                ),
              ),
            ])
          else
            Row(children: [
              Expanded(
                child: TextField(
                  controller: _ctrl,
                  keyboardType: const TextInputType.numberWithOptions(
                      decimal: true),
                  style: TextStyle(
                      color: context.textPri,
                      fontSize: 16,
                      fontWeight: FontWeight.w600),
                  decoration: InputDecoration(
                    hintText: '0.0',
                    hintStyle: TextStyle(color: context.textMut),
                    suffixText: 'U',
                    suffixStyle: TextStyle(
                        color: context.textSec,
                        fontWeight: FontWeight.w600),
                    contentPadding: const EdgeInsets.symmetric(
                        horizontal: 14, vertical: 12),
                    filled: true,
                    fillColor: context.appBg,
                    enabledBorder: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(12),
                      borderSide: BorderSide(color: context.borderC),
                    ),
                    focusedBorder: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(12),
                      borderSide: const BorderSide(
                          color: AppColors.accentGreen, width: 1.5),
                    ),
                  ),
                ),
              ),
              const SizedBox(width: 12),
              SizedBox(
                height: 48,
                child: ElevatedButton(
                  onPressed: _log,
                  style: ElevatedButton.styleFrom(
                    backgroundColor: AppColors.accentGreen,
                    foregroundColor: Colors.white,
                    shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(12)),
                    padding:
                        const EdgeInsets.symmetric(horizontal: 20),
                  ),
                  child: const Text(
                    'Log',
                    style: TextStyle(
                        fontWeight: FontWeight.w700, fontSize: 14),
                  ),
                ),
              ),
            ]),
        ],
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────

class _BolusBreakdown extends StatelessWidget {
  const _BolusBreakdown({required this.label, required this.value});

  final String label;
  final double value;

  @override
  Widget build(BuildContext context) {
    return Row(children: [
      Text(label,
          style: TextStyle(
              color: context.textMut, fontSize: 11)),
      const SizedBox(width: 6),
      Text(
        '${value.toStringAsFixed(1)} U',
        style: TextStyle(
          color: context.textSec,
          fontSize: 12,
          fontWeight: FontWeight.w600,
        ),
      ),
    ]);
  }
}
