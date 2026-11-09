import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:go_router/go_router.dart';
import '../../../core/constants/app_colors.dart';
import '../../../core/constants/app_spacing.dart';
import '../../../data/mock/mock_glucose.dart';
import '../../../data/models/meal_model.dart';
import '../../widgets/common/gradient_button.dart';

class FoodRecommendationScreen extends StatefulWidget {
  const FoodRecommendationScreen({super.key});

  @override
  State<FoodRecommendationScreen> createState() => _FoodRecommendationScreenState();
}

class _FoodRecommendationScreenState extends State<FoodRecommendationScreen> {
  String _search = '';
  FoodItem? _selected;
  bool _showResult = false;

  List<FoodItem> get _filtered => mockFoods
      .where((f) => f.name.toLowerCase().contains(_search.toLowerCase()))
      .toList();

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.darkBackground,
      appBar: AppBar(
        backgroundColor: AppColors.darkBackground,
        title: const Text('Food Advisor',
            style: TextStyle(fontWeight: FontWeight.w700)),
        leading: IconButton(
          icon: const Icon(Icons.keyboard_arrow_down_rounded, size: 28),
          onPressed: () => context.pop(),
        ),
      ),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.all(AppSpacing.screenPadding),
            child: Column(
              children: [
                // Search
                TextField(
                  decoration: InputDecoration(
                    hintText: 'Search foods...',
                    prefixIcon: const Icon(Icons.search_rounded, color: AppColors.textMutedDark),
                    suffixIcon: _search.isNotEmpty
                        ? IconButton(
                            icon: const Icon(Icons.clear_rounded,
                                color: AppColors.textMutedDark),
                            onPressed: () => setState(() => _search = ''),
                          )
                        : null,
                  ),
                  style: const TextStyle(color: AppColors.textPrimaryDark),
                  onChanged: (v) => setState(() {
                    _search = v;
                    _selected = null;
                    _showResult = false;
                  }),
                ),
              ],
            ),
          ),

          Expanded(
            child: AnimatedSwitcher(
              duration: const Duration(milliseconds: 350),
              child: _showResult && _selected != null
                  ? _RecommendationResult(
                      key: const ValueKey('result'),
                      food: _selected!,
                      onBack: () => setState(() {
                        _showResult = false;
                        _selected = null;
                      }),
                    )
                  : _FoodGrid(
                      key: const ValueKey('grid'),
                      foods: _filtered,
                      onSelect: (f) => setState(() {
                        _selected = f;
                        _showResult = true;
                      }),
                    ),
            ),
          ),
        ],
      ),
    );
  }
}

class _FoodGrid extends StatelessWidget {
  const _FoodGrid({super.key, required this.foods, required this.onSelect});

  final List<FoodItem> foods;
  final ValueChanged<FoodItem> onSelect;

  @override
  Widget build(BuildContext context) {
    return GridView.builder(
      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.screenPadding),
      gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: 2,
        childAspectRatio: 1.4,
        crossAxisSpacing: 12,
        mainAxisSpacing: 12,
      ),
      itemCount: foods.length,
      itemBuilder: (ctx, i) => _FoodCard(
        food: foods[i],
        onTap: () => onSelect(foods[i]),
      )
          .animate(delay: Duration(milliseconds: i * 50))
          .fadeIn(duration: 300.ms)
          .slideY(begin: 0.2, end: 0),
    );
  }
}

class _FoodCard extends StatelessWidget {
  const _FoodCard({required this.food, required this.onTap});

  final FoodItem food;
  final VoidCallback onTap;

  Color get _giColor {
    if (food.gi < 40) return AppColors.accentGreen;
    if (food.gi < 70) return AppColors.accentAmber;
    return AppColors.danger;
  }

  String get _giLabel {
    if (food.gi < 40) return 'Low GI';
    if (food.gi < 70) return 'Med GI';
    return 'High GI';
  }

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: AppColors.darkCard,
          borderRadius: BorderRadius.circular(AppSpacing.radiusXl),
          border: Border.all(color: AppColors.darkBorder),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(children: [
              Text(food.emoji, style: const TextStyle(fontSize: 28)),
              const Spacer(),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                decoration: BoxDecoration(
                  color: _giColor.withOpacity(0.12),
                  borderRadius: BorderRadius.circular(6),
                ),
                child: Text(
                  _giLabel,
                  style: TextStyle(
                    color: _giColor,
                    fontSize: 9,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
            ]),
            const SizedBox(height: 8),
            Text(
              food.name,
              style: const TextStyle(
                color: AppColors.textPrimaryDark,
                fontWeight: FontWeight.w600,
                fontSize: 13,
              ),
            ),
            Text(
              '${food.carbsPer100g.round()}g carbs/100g',
              style: const TextStyle(
                color: AppColors.textMutedDark,
                fontSize: 10,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _RecommendationResult extends StatelessWidget {
  const _RecommendationResult({
    super.key,
    required this.food,
    required this.onBack,
  });

  final FoodItem food;
  final VoidCallback onBack;

  double get _safePortion {
    if (food.gi > 60) return 80.0;
    if (food.gi > 40) return 120.0;
    return 180.0;
  }

  @override
  Widget build(BuildContext context) {
    final safeCarbs = _safePortion * food.carbsPer100g / 100;
    final impact = food.gi > 60 ? 'High' : food.gi > 40 ? 'Moderate' : 'Low';
    final impactColor = food.gi > 60
        ? AppColors.danger
        : food.gi > 40
            ? AppColors.warning
            : AppColors.accentGreen;

    return SingleChildScrollView(
      padding: const EdgeInsets.all(AppSpacing.screenPadding),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Header
          GestureDetector(
            onTap: onBack,
            child: const Row(children: [
              Icon(Icons.arrow_back_rounded,
                  color: AppColors.primary, size: 18),
              SizedBox(width: 4),
              Text('Back to foods',
                  style: TextStyle(color: AppColors.primary, fontSize: 13)),
            ]),
          ),

          const SizedBox(height: 16),

          // Main rec card
          Container(
            padding: const EdgeInsets.all(AppSpacing.cardPadding),
            decoration: BoxDecoration(
              gradient: const LinearGradient(
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
                colors: [Color(0xFF0D1A35), Color(0xFF0A1220)],
              ),
              borderRadius: BorderRadius.circular(AppSpacing.radiusXl),
              border: Border.all(color: AppColors.accentGreen.withOpacity(0.3)),
              boxShadow: [
                BoxShadow(
                  color: AppColors.accentGreen.withOpacity(0.08),
                  blurRadius: 24,
                  offset: const Offset(0, 8),
                ),
              ],
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(children: [
                  Text(food.emoji, style: const TextStyle(fontSize: 36)),
                  const SizedBox(width: 12),
                  Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text(
                      food.name,
                      style: const TextStyle(
                        color: AppColors.textPrimaryDark,
                        fontWeight: FontWeight.w700,
                        fontSize: 18,
                      ),
                    ),
                    Text(
                      food.category,
                      style: const TextStyle(
                          color: AppColors.textMutedDark, fontSize: 12),
                    ),
                  ]),
                ]),
                const SizedBox(height: 20),
                const Divider(color: AppColors.darkDivider),
                const SizedBox(height: 16),

                // Portion
                Row(children: [
                  _RecMetric(
                    label: 'Safe Portion',
                    value: '${_safePortion.round()}g',
                    color: AppColors.accentGreen,
                    icon: Icons.restaurant_rounded,
                  ),
                  const SizedBox(width: 12),
                  _RecMetric(
                    label: 'Est. Carbs',
                    value: '${safeCarbs.round()}g',
                    color: AppColors.primary,
                    icon: Icons.grain_rounded,
                  ),
                  const SizedBox(width: 12),
                  _RecMetric(
                    label: 'GI Impact',
                    value: impact,
                    color: impactColor,
                    icon: Icons.speed_rounded,
                  ),
                ]),

                const SizedBox(height: 16),
                const Divider(color: AppColors.darkDivider),
                const SizedBox(height: 12),

                Row(children: [
                  const Icon(Icons.lightbulb_rounded,
                      color: AppColors.accentCyan, size: 14),
                  const SizedBox(width: 6),
                  Expanded(
                    child: Text(
                      food.gi > 60
                          ? 'High GI food. Consider pairing with protein or fat to slow absorption. Pre-bolus 15 min before eating.'
                          : food.gi > 40
                              ? 'Moderate GI. Good choice. Bolus at mealtime or 5 min before.'
                              : 'Low GI food — minimal glucose spike expected. Great for stable control.',
                      style: const TextStyle(
                        color: AppColors.textSecondaryDark,
                        fontSize: 12,
                        height: 1.4,
                      ),
                    ),
                  ),
                ]),
              ],
            ),
          ),

          const SizedBox(height: 16),

          // Portion visual
          _PortionVisual(grams: _safePortion, food: food),

          const SizedBox(height: 20),

          GradientButton(
            label: 'Use This Portion',
            gradient: AppColors.successGradient,
            onPressed: () => context.pop(),
            icon: Icons.check_rounded,
          ),
        ],
      ),
    );
  }
}

class _RecMetric extends StatelessWidget {
  const _RecMetric({
    required this.label,
    required this.value,
    required this.color,
    required this.icon,
  });

  final String label;
  final String value;
  final Color color;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: Container(
        padding: const EdgeInsets.all(10),
        decoration: BoxDecoration(
          color: color.withOpacity(0.08),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: color.withOpacity(0.2)),
        ),
        child: Column(
          children: [
            Icon(icon, color: color, size: 18),
            const SizedBox(height: 4),
            Text(
              value,
              style: TextStyle(
                color: color,
                fontSize: 14,
                fontWeight: FontWeight.w700,
              ),
            ),
            Text(
              label,
              style: const TextStyle(
                color: AppColors.textMutedDark,
                fontSize: 9,
              ),
              textAlign: TextAlign.center,
            ),
          ],
        ),
      ),
    );
  }
}

class _PortionVisual extends StatelessWidget {
  const _PortionVisual({required this.grams, required this.food});

  final double grams;
  final FoodItem food;

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
          const Text(
            'Portion Size Reference',
            style: TextStyle(
              color: AppColors.textPrimaryDark,
              fontWeight: FontWeight.w600,
              fontSize: 13,
            ),
          ),
          const SizedBox(height: 12),
          Row(children: [
            Column(children: [
              Text(food.emoji, style: const TextStyle(fontSize: 40)),
              Text('${grams.round()}g',
                  style: const TextStyle(
                      color: AppColors.accentGreen, fontWeight: FontWeight.w700)),
              const Text('Recommended',
                  style: TextStyle(color: AppColors.textMutedDark, fontSize: 9)),
            ]),
            const SizedBox(width: 24),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _PctBar(label: '50g', value: 0.28, color: AppColors.accentGreen),
                  const SizedBox(height: 6),
                  _PctBar(label: '${grams.round()}g', value: grams / 200, color: AppColors.primary),
                  const SizedBox(height: 6),
                  _PctBar(label: '200g', value: 1.0, color: AppColors.danger),
                ],
              ),
            ),
          ]),
        ],
      ),
    );
  }
}

class _PctBar extends StatelessWidget {
  const _PctBar({required this.label, required this.value, required this.color});

  final String label;
  final double value;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        SizedBox(
          width: 36,
          child: Text(label,
              style: TextStyle(color: color, fontSize: 10, fontWeight: FontWeight.w600)),
        ),
        const SizedBox(width: 8),
        Expanded(
          child: ClipRRect(
            borderRadius: BorderRadius.circular(4),
            child: LinearProgressIndicator(
              value: value.clamp(0.0, 1.0),
              backgroundColor: AppColors.darkBorder,
              valueColor: AlwaysStoppedAnimation(color),
              minHeight: 8,
            ),
          ),
        ),
      ],
    );
  }
}
