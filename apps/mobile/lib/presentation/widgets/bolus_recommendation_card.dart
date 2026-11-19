import 'package:flutter/material.dart';

enum BolusRecommendationDemoState { meal, highGlucose }

class BolusRecommendationCard extends StatefulWidget {
  const BolusRecommendationCard({
    super.key,
    this.initialState = BolusRecommendationDemoState.meal,
  });

  final BolusRecommendationDemoState initialState;

  @override
  State<BolusRecommendationCard> createState() =>
      _BolusRecommendationCardState();
}

class _BolusRecommendationCardState extends State<BolusRecommendationCard> {
  static const _navy = Color(0xFF072E50);
  static const _muted = Color(0xFF5F7487);
  static const _iceBlue = Color(0xFFE1F0FA);
  static const _amberSurface = Color(0xFFFFF4DF);
  static const _amberText = Color(0xFF9A5700);

  late BolusRecommendationDemoState _state = widget.initialState;

  bool get _isMeal => _state == BolusRecommendationDemoState.meal;

  @override
  Widget build(BuildContext context) {
    final primary = Theme.of(context).colorScheme.primary;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Row(
              children: [
                Icon(Icons.calculate_outlined, color: _navy, size: 21),
                SizedBox(width: 8),
                Expanded(
                  child: Text(
                    'Bolus Recommendation',
                    style: TextStyle(
                      color: _navy,
                      fontSize: 17,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
                Text(
                  'Simulation preview',
                  style: TextStyle(
                    color: _muted,
                    fontSize: 11,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 14),
            SegmentedButton<BolusRecommendationDemoState>(
              segments: const [
                ButtonSegment(
                  value: BolusRecommendationDemoState.meal,
                  label: Text('Meal logged'),
                  icon: Icon(Icons.restaurant_outlined, size: 17),
                ),
                ButtonSegment(
                  value: BolusRecommendationDemoState.highGlucose,
                  label: Text('High glucose'),
                  icon: Icon(Icons.trending_up_rounded, size: 17),
                ),
              ],
              selected: {_state},
              onSelectionChanged: (selection) {
                setState(() => _state = selection.first);
              },
              showSelectedIcon: false,
              style: ButtonStyle(
                visualDensity: VisualDensity.compact,
                textStyle: WidgetStateProperty.all(
                  const TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
                ),
              ),
            ),
            const SizedBox(height: 16),
            Align(
              alignment: Alignment.centerLeft,
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 5),
                decoration: BoxDecoration(
                  color: _isMeal ? _iceBlue : _amberSurface,
                  borderRadius: BorderRadius.circular(7),
                ),
                child: Text(
                  _isMeal ? 'Meal logged' : 'High glucose',
                  style: TextStyle(
                    color: _isMeal ? primary : _amberText,
                    fontSize: 11,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
            ),
            const SizedBox(height: 8),
            Text(
              _isMeal ? 'Lunch · 45 g carbs' : 'Glucose above your target',
              style: const TextStyle(
                color: _navy,
                fontSize: 15,
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 3),
            Text(
              _isMeal
                  ? 'Meal context ready for simulation'
                  : '214 mg/dL · Sample reading at 23:00',
              style: const TextStyle(color: _muted, fontSize: 13),
            ),
            const SizedBox(height: 14),
            const Divider(height: 1),
            const SizedBox(height: 14),
            Row(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        _isMeal
                            ? 'Meal bolus estimate'
                            : 'Correction bolus estimate',
                        style: const TextStyle(color: _muted, fontSize: 13),
                      ),
                      const SizedBox(height: 3),
                      const Text(
                        '— U',
                        semanticsLabel: 'Dose unavailable',
                        style: TextStyle(
                          color: _navy,
                          fontSize: 25,
                          fontWeight: FontWeight.w800,
                        ),
                      ),
                    ],
                  ),
                ),
                OutlinedButton.icon(
                  key: const ValueKey('bolus-recommendation-review'),
                  onPressed: _showDetails,
                  icon: const Icon(Icons.expand_more_rounded, size: 18),
                  label: const Text('Review details'),
                  style: OutlinedButton.styleFrom(
                    foregroundColor: primary,
                    visualDensity: VisualDensity.compact,
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  void _showDetails() {
    final details = _isMeal
        ? const [
            ('Meal', 'Lunch'),
            ('Carbohydrates', '45 g'),
            ('Meal status', 'Logged'),
          ]
        : const [
            ('Current glucose', '214 mg/dL'),
            ('Sample target range', '70–180 mg/dL'),
            ('Reading time', '23:00'),
          ];
    final title = _isMeal ? 'Meal logged inputs' : 'High glucose inputs';

    showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      useSafeArea: true,
      builder: (context) => Padding(
        padding: EdgeInsets.fromLTRB(
          20,
          0,
          20,
          20 + MediaQuery.paddingOf(context).bottom,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              title,
              style: const TextStyle(
                color: _navy,
                fontSize: 19,
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 16),
            ...details.map(
              (detail) => Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: Row(
                  children: [
                    Expanded(
                      child: Text(
                        detail.$1,
                        style: const TextStyle(color: _muted),
                      ),
                    ),
                    Text(
                      detail.$2,
                      style: const TextStyle(
                        color: _navy,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ],
                ),
              ),
            ),
            const Text(
              'Visual prototype only. No dose is calculated or saved.',
              style: TextStyle(color: _muted, fontSize: 12),
            ),
          ],
        ),
      ),
    );
  }
}
